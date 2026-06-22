"""Hypothesis Predicate Language (HPL) — formal grammar for machine-executable hypotheses.

The HPL makes Hypothesis nodes machine-executable rather than just text.
Every other Phase 5 component depends on this foundational primitive.

Grammar supports:
    PREDICATE: Subject RelationshipType Object
        DURING TimeInterval[from, to, confidence:X]
        IMPLIES [ EvidenceType(params), ... ]
        FORBIDS [ EvidenceType(params), ... ]
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from lark import Lark, Transformer, v_args

logger = logging.getLogger(__name__)

# ── Lark Grammar Definition ─────────────────────────────────────────────

HPL_GRAMMAR = r"""
    start: predicate

    predicate: "PREDICATE:" entity relationship entity during_clause? implies_clause? forbids_clause?

    entity: ENTITY_TYPE "[" ENTITY_ID "]"
    relationship: RELATIONSHIP_NAME
    during_clause: "DURING" "TimeInterval" "[" TIMESTAMP "," TIMESTAMP "," "confidence:" NUMBER "]"

    implies_clause: "IMPLIES" "[" evidence_list "]"
    forbids_clause: "FORBIDS" "[" evidence_list "]"

    evidence_list: evidence_item ("," evidence_item)*
    evidence_item: EVIDENCE_TYPE "(" param_list? ")"
    param_list: param ("," param)*
    param: PARAM_KEY ":" PARAM_VALUE

    ENTITY_TYPE: /[A-Z][a-zA-Z]*/
    ENTITY_ID: /[a-zA-Z0-9_\-]+/
    RELATIONSHIP_NAME: /[A-Z_]+/
    EVIDENCE_TYPE: /[A-Za-z][A-Za-z0-9_]*/
    TIMESTAMP: /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z?/
    NUMBER: /\d+(\.\d+)?/
    PARAM_KEY: /[a-z][a-z_0-9]*/
    PARAM_VALUE: /[^\s,)]+/

    %import common.WS
    %ignore WS
"""

parser = Lark(HPL_GRAMMAR, parser="earley", ambiguity="resolve")


# ── Data Classes ─────────────────────────────────────────────────────────

@dataclass
class EntityRef:
    entity_type: str
    entity_id: str


@dataclass
class TimeInterval:
    from_ts: str
    to_ts: str
    confidence: float


@dataclass
class EvidenceItem:
    evidence_type: str
    params: dict = field(default_factory=dict)


@dataclass
class HypothesisPredicate:
    subject: EntityRef
    relationship: str
    obj: EntityRef
    during: Optional[TimeInterval] = None
    implies: list[EvidenceItem] = field(default_factory=list)
    forbids: list[EvidenceItem] = field(default_factory=list)


# ── Lark Tree → Python Objects Transformer ───────────────────────────────

@v_args(inline=True)
class HPLTransformer(Transformer):
    def start(self, predicate):
        return predicate

    def predicate(self, *args):
        subject = args[0]
        relationship = args[1]
        obj = args[2]
        during = None
        implies = []
        forbids = []
        for arg in args[3:]:
            if isinstance(arg, TimeInterval):
                during = arg
            elif isinstance(arg, tuple):
                if arg[0] == "implies":
                    implies = arg[1]
                elif arg[0] == "forbids":
                    forbids = arg[1]
        return HypothesisPredicate(
            subject=subject, relationship=relationship,
            obj=obj, during=during, implies=implies, forbids=forbids,
        )

    def entity(self, etype, eid):
        return EntityRef(entity_type=str(etype), entity_id=str(eid))

    def relationship(self, name):
        return str(name)

    def during_clause(self, from_ts, to_ts, conf):
        return TimeInterval(
            from_ts=str(from_ts), to_ts=str(to_ts), confidence=float(conf),
        )

    def implies_clause(self, evidence_list):
        return ("implies", evidence_list)

    def forbids_clause(self, evidence_list):
        return ("forbids", evidence_list)

    def evidence_list(self, *items):
        return list(items)

    def evidence_item(self, etype, *args):
        params = args[0] if args else {}
        return EvidenceItem(evidence_type=str(etype), params=params if isinstance(params, dict) else {})

    def param_list(self, *params):
        result = {}
        for p in params:
            result.update(p)
        return result

    def param(self, key, value):
        return {str(key): str(value)}


_transformer = HPLTransformer()


# ── Public API ───────────────────────────────────────────────────────────

def parse_hpl(hpl_string: str) -> HypothesisPredicate:
    """Parse an HPL string into a HypothesisPredicate object."""
    tree = parser.parse(hpl_string)
    return _transformer.transform(tree)


def serialize_hpl(pred: HypothesisPredicate) -> str:
    """Serialize a HypothesisPredicate back to an HPL string."""
    parts = [f"PREDICATE: {pred.subject.entity_type}[{pred.subject.entity_id}] "
             f"{pred.relationship} {pred.obj.entity_type}[{pred.obj.entity_id}]"]

    if pred.during:
        parts.append(
            f"  DURING TimeInterval[{pred.during.from_ts}, "
            f"{pred.during.to_ts}, confidence:{pred.during.confidence}]"
        )

    if pred.implies:
        items = []
        for ei in pred.implies:
            params_str = ", ".join(f"{k}: {v}" for k, v in ei.params.items())
            items.append(f"{ei.evidence_type}({params_str})")
        parts.append(f"  IMPLIES [{', '.join(items)}]")

    if pred.forbids:
        items = []
        for ei in pred.forbids:
            params_str = ", ".join(f"{k}: {v}" for k, v in ei.params.items())
            items.append(f"{ei.evidence_type}({params_str})")
        parts.append(f"  FORBIDS [{', '.join(items)}]")

    return "\n".join(parts)


def validate_hpl_entities(pred: HypothesisPredicate, case_id: str) -> list[str]:
    """
    Validate that entity references in the predicate exist in Neo4j.
    Returns list of validation error strings (empty = valid).
    """
    from app.graph.driver import get_neo4j_client
    client = get_neo4j_client()
    errors = []

    for ref in [pred.subject, pred.obj]:
        result = client.execute_read(
            f"MATCH (n:{ref.entity_type} {{id: $eid, case_id: $cid}}) RETURN n.id AS id",
            {"eid": ref.entity_id, "cid": case_id},
        )
        if not result:
            errors.append(
                f"Entity {ref.entity_type}[{ref.entity_id}] not found in case {case_id}"
            )

    return errors


def extract_evidence_lists(predicates: list[str]) -> tuple[list[dict], list[dict]]:
    """
    Parse multiple HPL strings and extract combined implied/forbidden evidence.
    Returns (implied_evidence, forbidden_evidence) as JSONB-ready lists.
    """
    implied = []
    forbidden = []

    for hpl_str in predicates:
        try:
            pred = parse_hpl(hpl_str)
            for ei in pred.implies:
                implied.append({
                    "evidence_type": ei.evidence_type,
                    "params": ei.params,
                    "source_predicate": hpl_str[:100],
                })
            for ei in pred.forbids:
                forbidden.append({
                    "evidence_type": ei.evidence_type,
                    "params": ei.params,
                    "source_predicate": hpl_str[:100],
                })
        except Exception as e:
            logger.warning("Failed to parse HPL: %s — %s", hpl_str[:50], e)

    return implied, forbidden


def check_implied_evidence_status(case_id: str, implied_evidence: list[dict]) -> list[dict]:
    """
    For each implied evidence item, check if matching evidence exists in the graph.

    Returns list of {evidence_type, params, status: found|absent|not_checked}.
    """
    from app.graph.driver import get_neo4j_client
    client = get_neo4j_client()
    results = []

    # Evidence type checkers — each maps an evidence_type to a Cypher check
    checkers = {
        "CellTowerPing": _check_cell_tower_ping,
        "GPSRecord": _check_gps_record,
        "CCTVFrame": _check_cctv_frame,
        "CommunicationRecord": _check_communication_record,
    }

    for item in implied_evidence:
        etype = item.get("evidence_type", "")
        params = item.get("params", {})
        checker = checkers.get(etype)

        if checker:
            status = checker(client, case_id, params)
        else:
            status = "not_checked"

        results.append({
            "evidence_type": etype,
            "params": params,
            "status": status,
        })

    return results


def _check_cell_tower_ping(client, case_id: str, params: dict) -> str:
    """Check for Event(cell_tower) AT Location in time window."""
    window = params.get("window", "")
    location_area = params.get("location_area", "")
    parts = window.split("/") if "/" in window else [window, window]

    result = client.execute_read(
        """
        MATCH (e:Event {case_id: $cid, event_type: 'cell_tower'})-[:AT]->(l:Location)
        WHERE l.id = $loc OR l.display_name = $loc
        AND e.valid_from >= $from AND e.valid_from <= $to
        RETURN count(e) AS cnt
        """,
        {"cid": case_id, "loc": location_area, "from": parts[0], "to": parts[-1]},
    )
    return "found" if result and result[0]["cnt"] > 0 else "absent"


def _check_gps_record(client, case_id: str, params: dict) -> str:
    """Check for AT relationship with GPS-type Location in time window."""
    window = params.get("window", "")
    person = params.get("person", "")
    parts = window.split("/") if "/" in window else [window, window]

    result = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})-[r:AT]->(l:Location)
        WHERE (p.id = $pid OR p.display_name = $pid)
        AND r.valid_from >= $from AND r.valid_from <= $to
        RETURN count(r) AS cnt
        """,
        {"cid": case_id, "pid": person, "from": parts[0], "to": parts[-1]},
    )
    return "found" if result and result[0]["cnt"] > 0 else "absent"


def _check_cctv_frame(client, case_id: str, params: dict) -> str:
    """Check for Event(cctv) AT Location in time window."""
    window = params.get("window", "")
    location = params.get("location", "")
    parts = window.split("/") if "/" in window else [window, window]

    result = client.execute_read(
        """
        MATCH (e:Event {case_id: $cid})-[:AT]->(l:Location)
        WHERE (e.event_type = 'cctv' OR e.event_type = 'video')
        AND (l.id = $loc OR l.display_name = $loc)
        AND e.valid_from >= $from AND e.valid_from <= $to
        RETURN count(e) AS cnt
        """,
        {"cid": case_id, "loc": location, "from": parts[0], "to": parts[-1]},
    )
    return "found" if result and result[0]["cnt"] > 0 else "absent"


def _check_communication_record(client, case_id: str, params: dict) -> str:
    """Check for COMMUNICATED_WITH relationship in time window."""
    window = params.get("window", "")
    parts = window.split("/") if "/" in window else [window, window]

    result = client.execute_read(
        """
        MATCH (a)-[r:COMMUNICATED_WITH]->(b)
        WHERE a.case_id = $cid
        AND r.valid_from >= $from AND r.valid_from <= $to
        RETURN count(r) AS cnt
        """,
        {"cid": case_id, "from": parts[0], "to": parts[-1]},
    )
    return "found" if result and result[0]["cnt"] > 0 else "absent"
