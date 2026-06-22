"""Deception Detection Service — model-serving component.

Placeholder model interface with a clearly documented swap point.
To integrate a real model (e.g., EfficientNet-B4 from CyberLens-X):
    1. Replace PlaceholderDetector with your model class
    2. Implement the detect() method with actual inference
    3. Update model_name and model_version
    4. Add GPU dependencies (torch, torchvision) to requirements.txt
"""

import io
import hashlib
import logging
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Deception Detection Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Model Interface ──────────────────────────────────────────────────────

class DetectionResult(BaseModel):
    deception_score: float    # 0-1 (0 = genuine, 1 = manipulated)
    confidence: float         # 0-1
    model_name: str
    model_version: str
    explanation: str
    content_hash: str


class PlaceholderDetector:
    """
    Placeholder model — returns deterministic scores based on content hash.

    *** SWAP POINT ***
    Replace this class with your actual deepfake detection model.
    The interface contract is:
        detect(content_bytes: bytes, content_type: str) -> DetectionResult
    """
    model_name = "placeholder_detector"
    model_version = "0.1.0"

    def detect(self, content_bytes: bytes, content_type: str) -> DetectionResult:
        # Deterministic score from content hash (for testability)
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        # Use last byte of hash to generate a score
        hash_val = int(content_hash[-2:], 16)
        score = hash_val / 255.0

        return DetectionResult(
            deception_score=round(score, 4),
            confidence=0.5,  # Placeholder has low confidence
            model_name=self.model_name,
            model_version=self.model_version,
            explanation="Placeholder model — score derived from content hash. "
                        "Replace with actual deepfake detection model for real assessments.",
            content_hash=content_hash,
        )


# ── Stylometric Heuristic ────────────────────────────────────────────────

class StylometricHeuristic:
    """
    Lightweight synthetic-text heuristic for communication records.
    Compares message style against a reference distribution.

    This is EXPLICITLY a heuristic, NOT a trained classifier.
    Confidence is capped at 0.3 and labeled clearly.
    """
    model_name = "stylometric_heuristic_v1"
    model_version = "0.1.0"

    def analyze(
        self,
        message: str,
        reference_messages: list[str] = None,
    ) -> DetectionResult:
        import statistics

        content_hash = hashlib.sha256(message.encode()).hexdigest()

        if not reference_messages or len(reference_messages) < 3:
            return DetectionResult(
                deception_score=0.0,
                confidence=0.1,
                model_name=self.model_name,
                model_version=self.model_version,
                explanation="Insufficient reference messages for comparison",
                content_hash=content_hash,
            )

        # Feature 1: sentence length variance
        def avg_sentence_len(text):
            sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
            return statistics.mean([len(s.split()) for s in sentences]) if sentences else 0

        msg_avg = avg_sentence_len(message)
        ref_avgs = [avg_sentence_len(m) for m in reference_messages]
        ref_mean = statistics.mean(ref_avgs)
        ref_std = statistics.stdev(ref_avgs) if len(ref_avgs) > 1 else 1.0

        len_z = abs(msg_avg - ref_mean) / ref_std if ref_std > 0 else 0

        # Feature 2: vocabulary repetition rate
        def vocab_repetition(text):
            words = text.lower().split()
            return 1 - (len(set(words)) / len(words)) if words else 0

        msg_rep = vocab_repetition(message)
        ref_reps = [vocab_repetition(m) for m in reference_messages]
        ref_rep_mean = statistics.mean(ref_reps)
        ref_rep_std = statistics.stdev(ref_reps) if len(ref_reps) > 1 else 0.1

        rep_z = abs(msg_rep - ref_rep_mean) / ref_rep_std if ref_rep_std > 0 else 0

        # Combined deviation score
        combined_z = (len_z + rep_z) / 2
        score = min(1.0, combined_z / 4.0)  # Scale z-score to 0-1

        return DetectionResult(
            deception_score=round(score, 4),
            confidence=min(0.3, score),  # Explicitly low confidence
            model_name=self.model_name,
            model_version=self.model_version,
            explanation=f"Stylometric deviation: sentence_length_z={len_z:.2f}, "
                        f"vocab_repetition_z={rep_z:.2f}. "
                        f"This is a heuristic, not a trained classifier.",
            content_hash=content_hash,
        )


# ── Instances ────────────────────────────────────────────────────────────

_detector = PlaceholderDetector()
_stylometric = StylometricHeuristic()


# ── Endpoints ────────────────────────────────────────────────────────────

@app.post("/detect/media")
async def detect_media(
    file: UploadFile = File(...),
    content_type: Optional[str] = Form(None),
):
    """Assess an image/video/audio file for signs of manipulation."""
    content = await file.read()
    ct = content_type or file.content_type or "application/octet-stream"
    result = _detector.detect(content, ct)
    return result.model_dump()


class TextAnalysisRequest(BaseModel):
    message: str
    reference_messages: list[str] = []


@app.post("/detect/text")
def detect_text(body: TextAnalysisRequest):
    """Assess a text message using stylometric heuristic."""
    result = _stylometric.analyze(body.message, body.reference_messages)
    return result.model_dump()


@app.get("/health")
def health():
    return {
        "service": "deception-detection",
        "media_model": _detector.model_name,
        "text_model": _stylometric.model_name,
    }
