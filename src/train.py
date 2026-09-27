# train.py
"""Placeholder/training entry point for a custom gesture classifier.

The live app (``main.py``) uses MediaPipe's pre-trained hand landmarker
plus a small rule-based finger counter, so no trained model is required.
This module provides the skeleton for training your own classifier on
top of the 21 hand landmarks (e.g. with scikit-learn) without running
anything on import.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def extract_features(hand_landmarks):
    """Flatten 21 normalized landmarks to a 63-dim feature vector."""
    feats = []
    for lm in hand_landmarks:
        feats.extend([float(lm.x), float(lm.y), float(getattr(lm, "z", 0.0))])
    if len(feats) != 63:
        raise ValueError(f"Expected 21 landmarks (63 values), got {len(feats)}")
    return feats


def load_dataset(data_dir):
    """Load a landmark dataset. Override with your own format."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Dataset dir not found: {data_dir}")
    raise NotImplementedError(
        "No dataset loader implemented yet. Store samples as e.g. "
        "``<data_dir>/<gesture>/*.npy`` (63-dim vectors) and implement "
        "loading here."
    )


def train(data_dir="data", out_path="models/gesture_classifier.pkl"):
    """Train a classifier; currently a stub."""
    print(f"Would train on {data_dir} and write {out_path}.")
    print("Training not implemented yet: implement load_dataset() + a "
          "scikit-learn pipeline (e.g. StandardScaler + RandomForest).")
    raise NotImplementedError("Training script – not implemented yet.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train gesture classifier (stub)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", default="models/gesture_classifier.pkl")
    args = parser.parse_args(argv)
    train(args.data_dir, args.out)


if __name__ == "__main__":
    main()