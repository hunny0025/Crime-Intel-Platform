import asyncio
import os
import logging
from typing import Dict, List, Any, Callable, Optional

logger = logging.getLogger(__name__)

class AsyncDebouncer:
    def __init__(self):
        self.buffers: Dict[str, List[Dict[str, Any]]] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self.callback: Optional[Callable[[str, Dict[str, Any]], Any]] = None

    def set_callback(self, callback: Callable[[str, Dict[str, Any]], Any]):
        self.callback = callback

    def add(self, case_id: str, payload: Dict[str, Any]):
        case_id_str = str(case_id)
        if case_id_str not in self.buffers:
            self.buffers[case_id_str] = []
        self.buffers[case_id_str].append(payload)

        # Cancel existing task if any
        if case_id_str in self.tasks:
            self.tasks[case_id_str].cancel()

        # Create new debounced task
        ms = int(os.getenv("AIRE_DEBOUNCE_MS", "2000"))
        delay = ms / 1000.0

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        task = loop.create_task(self._wait_and_emit(case_id_str, delay))
        self.tasks[case_id_str] = task

    async def _wait_and_emit(self, case_id_str: str, delay: float):
        try:
            await asyncio.sleep(delay)
            # Emit batch event
            payloads = self.buffers.pop(case_id_str, [])
            self.tasks.pop(case_id_str, None)

            # Merge payloads
            merged_nodes = []
            merged_rels = []
            merged_touched = []
            for p in payloads:
                node_id = p.get("node_id")
                new_nodes = p.get("new_node_ids") or p.get("node_ids")
                if isinstance(new_nodes, list):
                    merged_nodes.extend(new_nodes)
                elif node_id:
                    merged_nodes.append(node_id)

                rels = p.get("new_relationship_ids") or p.get("relationship_ids")
                if isinstance(rels, list):
                    merged_rels.extend(rels)

                touched = p.get("touched_entities")
                if isinstance(touched, list):
                    merged_touched.extend(touched)
                elif node_id:
                    merged_touched.append(node_id)

            merged_nodes = list(set(str(n) for n in merged_nodes if n))
            merged_rels = list(set(str(r) for r in merged_rels if r))
            merged_touched = list(set(str(t) for t in merged_touched if t))

            batch_payload = {
                "case_id": case_id_str,
                "event_type": "graph.batch_updated",
                "node_id": merged_nodes[0] if merged_nodes else "",
                "node_ids": merged_nodes,
                "new_node_ids": merged_nodes,
                "relationship_ids": merged_rels,
                "new_relationship_ids": merged_rels,
                "touched_entities": merged_touched,
            }

            if self.callback:
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback(case_id_str, batch_payload)
                else:
                    self.callback(case_id_str, batch_payload)
        except asyncio.CancelledError:
            # Task was cancelled because new event arrived, normal behavior
            pass
        except Exception as e:
            logger.error(f"Error in debouncer callback: {e}", exc_info=True)

    def get_buffer_size(self, case_id: str) -> int:
        return len(self.buffers.get(str(case_id), []))

debouncer = AsyncDebouncer()
