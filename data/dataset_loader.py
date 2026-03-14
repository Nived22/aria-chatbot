import re
import os
import torch
import pandas as pd
from torch.utils.data import Dataset

TWCS_PATH = "/Users/nivedkk/Downloads/archive (3)/twcs/twcs.csv"

# ── Frustration scoring heuristics ───────────────────────────────────────────
_HIGH_PATTERNS = [
    r"\b(unacceptable|disgusting|terrible|awful|outrageous|appalling|worst|scam|fraud|lied|lying|useless|incompetent|ridiculous)\b",
    r"\bnever (again|using|buying|coming back|recommend)\b",
    r"\bworst\b.{0,20}\b(service|experience|company|ever)\b",
    r"[A-Z]{4,}",       # long caps e.g. DISGUSTING
    r"!{3,}",           # 3+ exclamation marks
    r"\b(furious|livid|outraged|disgusted|infuriated)\b",
    r"\b(scam|rip.?off|robbery|theft|stole)\b",
]

_MODERATE_PATTERNS = [
    r"\b(still|waiting|waited)\b.{0,20}\b(no|nothing|not|never)\b",
    r"\b(wrong|broken|damaged|missing|lost|late|delayed|faulty|defective)\b",
    r"\b(frustrated|annoyed|disappointed|upset|unhappy|dissatisfied)\b",
    r"\bno (response|reply|help|support|one)\b",
    r"!{2}",
    r"\b(issue|problem|complaint|concern)\b",
    r"\b(days|weeks|hours|month).{0,15}\b(waiting|wait|nothing|no reply)\b",
    r"\b(fix|resolve|sort|help).{0,10}(please|now|immediately|asap|urgent)\b",
]

_POSITIVE_PATTERNS = [
    r"\b(thank|thanks|appreciate|grateful|great|excellent|amazing|awesome|love|happy|pleased|satisfied|perfect|wonderful)\b",
    r"\b(good|nice|well|helpful|brilliant|fantastic)\b",
]


def _clean_tweet(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _score_frustration(text: str) -> float:
    h = sum(1 for p in _HIGH_PATTERNS     if re.search(p, text, re.IGNORECASE))
    m = sum(1 for p in _MODERATE_PATTERNS if re.search(p, text, re.IGNORECASE))
    if h >= 2: return min(0.60 + h * 0.08, 0.95)
    if h == 1: return round(0.65 + m * 0.03, 2)
    if m >= 2: return round(0.50 + m * 0.03, 2)
    if m == 1: return 0.45
    return 0.25


def _score_sentiment(text: str) -> int:
    """Returns 0=negative, 1=neutral, 2=positive for Phase 1."""
    pos = sum(1 for p in _POSITIVE_PATTERNS if re.search(p, text, re.IGNORECASE))
    neg = sum(1 for p in _HIGH_PATTERNS + _MODERATE_PATTERNS[:4]
              if re.search(p, text, re.IGNORECASE))
    if pos > neg:   return 2   # positive
    if neg > pos:   return 0   # negative
    return 1                    # neutral


# Max examples per phase — balanced for accuracy vs speed on Mac CPU
# New chunked loader scans whole file for diversity so accuracy is much better
MAX_PHASE1 = 12_000   # 4,000 per sentiment class (balanced)
MAX_PHASE2 = 8_000    # high frustration examples
MAX_PHASE3 = 8_000    # moderate frustration examples
MAX_PHASE4 = 15_000   # full dataset final pass


def _load_base_df(path: str = None, max_rows: int = None) -> pd.DataFrame:
    """
    Load and clean twcs CSV using chunked reading to avoid RAM crashes.
    Reads entire file in chunks but only keeps a small sample from each
    chunk — this ensures diversity across the whole dataset.
    """
    path     = path or TWCS_PATH
    max_rows = max_rows or 10_000
    print(f"[DataLoader] Reading {path} (chunked, target: {max_rows:,} diverse rows)...")

    collected  = []
    total_read = 0
    chunk_size = 100_000   # read 100k at a time
    sample_per_chunk = max(50, max_rows // 20)  # take small slice from each chunk

    for chunk in pd.read_csv(path, chunksize=chunk_size,
                              on_bad_lines="skip", low_memory=False):
        total_read += len(chunk)

        # Keep only inbound customer messages
        chunk = chunk[chunk["inbound"] == True].copy()
        chunk["clean_text"] = chunk["text"].apply(_clean_tweet)
        chunk = chunk[chunk["clean_text"].str.len() > 8]

        if len(chunk) == 0:
            continue

        # Take a small diverse sample from this chunk
        n = min(sample_per_chunk, len(chunk))
        collected.append(chunk[["clean_text"]].sample(n, random_state=42))

    print(f"  → Scanned {total_read:,} total rows across whole file")

    df = pd.concat(collected, ignore_index=True)

    # Shuffle and cap to max_rows
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    if len(df) > max_rows:
        df = df.iloc[:max_rows]

    print(f"  → {len(df):,} diverse customer messages collected")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Sentiment Classification
# Used to fine-tune RoBERTa for positive / neutral / negative sentiment
# ─────────────────────────────────────────────────────────────────────────────
def load_phase1_sentiment(path: str = None):
    """
    Returns list of {"text": str, "label": int} where label is 0/1/2.
    Balanced across sentiment classes.
    """
    print("\n[DataLoader] Phase 1 — Sentiment Classification")
    df = _load_base_df(path)
    df["label"] = df["clean_text"].apply(_score_sentiment)

    # Balance classes
    min_class = df["label"].value_counts().min()
    balanced  = pd.concat([
        df[df["label"] == l].sample(min_class, random_state=42)
        for l in [0, 1, 2]
    ]).sample(frac=1, random_state=42).reset_index(drop=True)

    examples = [{"text": r["clean_text"], "label": int(r["label"])}
                for _, r in balanced.iterrows()]

    counts = balanced["label"].value_counts().sort_index()
    print(f"  Negative: {counts.get(0,0):,} | Neutral: {counts.get(1,0):,} | Positive: {counts.get(2,0):,}")
    print(f"  → {len(examples):,} total Phase 1 examples")
    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — High Frustration Examples
# Focuses on clearly frustrated messages (score >= 0.65)
# ─────────────────────────────────────────────────────────────────────────────
def load_phase2_high_frustration(path: str = None):
    """
    Returns list of {"text": str, "frustration_score": float}
    Only high frustration examples (>= 0.65) for precise upper-range training.
    """
    print("\n[DataLoader] Phase 2 — High Frustration Examples")
    df = _load_base_df(path)
    df["frustration_score"] = df["clean_text"].apply(_score_frustration)
    df = df[df["frustration_score"] >= 0.65]

    examples = [{"text": r["clean_text"], "frustration_score": round(r["frustration_score"], 2)}
                for _, r in df.iterrows()]

    print(f"  Score range: {df['frustration_score'].min():.2f} – {df['frustration_score'].max():.2f}")
    print(f"  → {len(examples):,} high frustration examples")
    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Moderate Frustration Examples
# Mid-range messages (0.30 – 0.65) for nuanced detection
# ─────────────────────────────────────────────────────────────────────────────
def load_phase3_moderate_frustration(path: str = None):
    """
    Returns list of {"text": str, "frustration_score": float}
    Moderate range examples. Falls back to wider range if too few found.
    """
    print("\n[DataLoader] Phase 3 — Moderate Frustration Examples")
    df = _load_base_df(path, max_rows=MAX_PHASE3 * 4)
    df["frustration_score"] = df["clean_text"].apply(_score_frustration)

    # Try moderate range first
    df_mod = df[(df["frustration_score"] >= 0.30) & (df["frustration_score"] < 0.65)].copy()
    print(f"  Found {len(df_mod):,} moderate examples (0.30-0.65)")

    # Too few — widen range
    if len(df_mod) < 500:
        print("  Too few — widening range to 0.25-0.75")
        df_mod = df[(df["frustration_score"] >= 0.25) & (df["frustration_score"] < 0.75)].copy()
        print(f"  Found {len(df_mod):,} after widening")

    # Still too few — use everything
    if len(df_mod) < 200:
        print("  Still too few — using full dataset for Phase 3")
        df_mod = df.copy()

    if len(df_mod) > MAX_PHASE3:
        df_mod = df_mod.sample(MAX_PHASE3, random_state=42)

    examples = [{"text": r["clean_text"], "frustration_score": round(r["frustration_score"], 2)}
                for _, r in df_mod.iterrows()]

    print(f"  Score range: {df_mod['frustration_score'].min():.2f} – {df_mod['frustration_score'].max():.2f}")
    print(f"  → {len(examples):,} Phase 3 examples")
    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Full Dataset (all customer messages)
# Complete training set combining all frustration levels
# ─────────────────────────────────────────────────────────────────────────────
def load_phase4_full(path: str = None):
    """
    Returns all customer messages with frustration scores.
    Used for final fine-tuning pass across full score range.
    """
    print("\n[DataLoader] Phase 4 — Full Dataset")
    df = _load_base_df(path)
    df["frustration_score"] = df["clean_text"].apply(_score_frustration)

    examples = [{"text": r["clean_text"], "frustration_score": round(r["frustration_score"], 2)}
                for _, r in df.iterrows()]

    scores = df["frustration_score"]
    high   = (scores >= 0.65).sum()
    mod    = ((scores >= 0.45) & (scores < 0.65)).sum()
    low    = (scores < 0.45).sum()
    print(f"  High (>=0.65):      {high:,} ({high/len(df)*100:.1f}%)")
    print(f"  Moderate (0.45-0.65): {mod:,} ({mod/len(df)*100:.1f}%)")
    print(f"  Low (<0.45):        {low:,} ({low/len(df)*100:.1f}%)")
    print(f"  → {len(examples):,} total Phase 4 examples")
    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Keep old function names as aliases for backward compatibility
# (so evaluation scripts and notebooks don't break)
# ─────────────────────────────────────────────────────────────────────────────
def load_phase4_twitter(csv_path: str = None):
    return load_phase4_full(csv_path)

def load_phase2_emowoz():
    return load_phase2_high_frustration()

def load_phase3_bitext(frustrated_only=True):
    return load_phase3_moderate_frustration()

def emowoz_to_frustration(emotion_id: int) -> float:
    # kept for backward compatibility
    mapping = {0:0.10,1:0.05,2:0.75,3:0.10,4:0.40,5:0.65,6:0.95}
    return mapping.get(int(emotion_id), 0.1)

def load_synthetic():
    # Return empty list — synthetic data no longer needed
    return []


# ─────────────────────────────────────────────────────────────────────────────
# PyTorch Dataset Wrapper
# ─────────────────────────────────────────────────────────────────────────────
class FrustrationDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt"
        )
        self.labels = torch.tensor(labels, dtype=torch.float32)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return {
            "input_ids":      self.encodings["input_ids"][idx],
            "attention_mask": self.encodings["attention_mask"][idx],
            "labels":         self.labels[idx]
        }


class SentimentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt"
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return {
            "input_ids":      self.encodings["input_ids"][idx],
            "attention_mask": self.encodings["attention_mask"][idx],
            "labels":         self.labels[idx]
        }