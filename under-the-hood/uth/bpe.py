"""Byte-pair encoding from scratch: how text becomes the tokens you are billed for.

Start from raw UTF-8 bytes (256 symbols, so any text can be encoded), then repeatedly merge the most frequent
adjacent pair into a new symbol. Merges learned on one kind of text compress that text well and other text badly:
the same sentence costs more tokens in a language the tokenizer saw little of.

    uv run python -m uth.bpe
"""

from collections import Counter
from itertools import pairwise

CORPUS = (
    "Hello, I would like to return my order. The tent arrived damaged and the poles are bent. "
    "Can you refund the order to my card? My order number is 1042. Thank you for your help. "
    "Your refund has been approved and will reach your card within five working days. "
    "To return an item, start a return within thirty days of delivery and print the return label. "
    "I cannot sign in to my account. My account is locked after too many attempts. "
    "Please reset my password and unlock my account so I can track my order. "
) * 20


def pairs(ids: list[int]) -> Counter:
    return Counter(pairwise(ids))


def merge(ids: list[int], pair: tuple[int, int], new: int) -> list[int]:
    out, i = [], 0
    while i < len(ids):
        if i < len(ids) - 1 and (ids[i], ids[i + 1]) == pair:
            out.append(new)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out


class BPE:
    def __init__(self, merges: dict[tuple[int, int], int]):
        self.merges = merges  # in the order they were learned; later merges build on earlier ones
        self.vocab = {i: bytes([i]) for i in range(256)}
        for (a, b), new in merges.items():
            self.vocab[new] = self.vocab[a] + self.vocab[b]

    @classmethod
    def train(cls, text: str, vocab_size: int) -> "BPE":
        ids, merges = list(text.encode("utf-8")), {}
        for new in range(256, vocab_size):
            counts = pairs(ids)
            if not counts:
                break
            best = max(counts, key=counts.get)
            if counts[best] < 2:
                break  # nothing left worth merging
            ids = merge(ids, best, new)
            merges[best] = new
        return cls(merges)

    def encode(self, text: str) -> list[int]:
        ids = list(text.encode("utf-8"))
        while len(ids) > 1:
            # apply the earliest-learned merge present, exactly as training did
            pair = min(pairs(ids), key=lambda p: self.merges.get(p, float("inf")))
            if pair not in self.merges:
                break
            ids = merge(ids, pair, self.merges[pair])
        return ids

    def decode(self, ids: list[int]) -> str:
        return b"".join(self.vocab[i] for i in ids).decode("utf-8", errors="replace")

    def pieces(self, text: str) -> list[str]:
        return [self.vocab[i].decode("utf-8", errors="replace") for i in self.encode(text)]


SAMPLES = {
    "English": "My order arrived damaged. Can you refund it to my card?",
    "German": "Meine Bestellung kam beschädigt an. Können Sie den Betrag auf meine Karte erstatten?",
    "Hindi": "मेरा ऑर्डर खराब हालत में आया। क्या आप मेरे कार्ड पर पैसे वापस कर सकते हैं?",
}


def main() -> None:
    bpe = BPE.train(CORPUS, vocab_size=512)
    print(f"Trained {len(bpe.merges)} merges on {len(CORPUS):,} characters of English support text.\n")
    print("How the first sentence is split:")
    print(" | ".join(bpe.pieces(SAMPLES["English"])), "\n")
    print(f"{'language':<9} {'chars':>6} {'bytes':>6} {'tokens':>7} {'chars per token':>16}")
    for lang, text in SAMPLES.items():
        n = len(bpe.encode(text))
        print(f"{lang:<9} {len(text):>6} {len(text.encode()):>6} {n:>7} {len(text) / n:>16.2f}")
    print("\nSame request, same meaning: the tokenizer only learned English, so other languages pay more.")


if __name__ == "__main__":
    main()
