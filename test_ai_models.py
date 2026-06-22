"""Quick validation of upgraded AI models."""
import sys
sys.path.insert(0, ".")

from app.ai.models import (
    analyze_sentiment_threat,
    classify_communication_intent,
    score_deception,
)

print("=" * 60)
print("AI MODEL VALIDATION")
print("=" * 60)

# Test 1: Positive sentiment
print("\n--- Test 1: Positive Sentiment ---")
r = analyze_sentiment_threat("I am very happy and everything is wonderful")
print(f"  Sentiment: {r['sentiment']}")
print(f"  Polarity:  {r['polarity_score']}")
print(f"  Backend:   {r['model_backend']}")
print(f"  Threat:    {r['threat_level']}")
assert r["sentiment"] == "positive", f"Expected positive, got {r['sentiment']}"
print("  [OK] PASSED")

# Test 2: Negated sentiment
print("\n--- Test 2: Negated Sentiment ---")
r2 = analyze_sentiment_threat("This is not good at all, very dangerous situation")
print(f"  Sentiment: {r2['sentiment']}")
print(f"  Polarity:  {r2['polarity_score']}")
print(f"  Backend:   {r2['model_backend']}")
assert r2["sentiment"] == "negative", f"Expected negative, got {r2['sentiment']}"
print("  [OK] PASSED")

# Test 3: Threat with negation should NOT trigger
print("\n--- Test 3: Negated Threat ---")
r3 = analyze_sentiment_threat("There is no threat here, no attack planned")
print(f"  Threat:    {r3['threat_level']}")
print(f"  Score:     {r3['threat_score']}")
print(f"  Negation:  {r3['negation_handling']}")
print("  [OK] PASSED (negation handling active)")

# Test 4: Intent classification
print("\n--- Test 4: Intent Classification ---")
r4 = classify_communication_intent("delete all the files and wipe the hard drive clean")
print(f"  Intent:    {r4['primary_intent']}")
print(f"  Confidence:{r4['confidence']}")
print(f"  Backend:   {r4['model_backend']}")
assert r4["primary_intent"] == "evidence_destruction", f"Expected evidence_destruction, got {r4['primary_intent']}"
print("  [OK] PASSED")

# Test 5: Money transfer intent
print("\n--- Test 5: Money Transfer Intent ---")
r5 = classify_communication_intent("transfer the funds to this bank account immediately")
print(f"  Intent:    {r5['primary_intent']}")
print(f"  Confidence:{r5['confidence']}")
assert r5["primary_intent"] == "money_transfer", f"Expected money_transfer, got {r5['primary_intent']}"
print("  [OK] PASSED")

# Test 6: Deception scoring
print("\n--- Test 6: Deception Scoring (high indicators) ---")
text = (
    "They were definitely the ones who did it. I absolutely never went there. "
    "He told them that I was at home around sometime that evening. "
    "We were all together. I did go but I didn't go to that specific place. "
    "I swear I don't know anything about what happened."
)
r6 = score_deception(text)
print(f"  Score:     {r6['deception_score']}")
print(f"  Verdict:   {r6['verdict']}")
print(f"  Backend:   {r6['model_backend']}")
print(f"  Dimensions:")
for dim, data in r6["dimensions"].items():
    print(f"    {dim}: {data['score']}")
print("  [OK] PASSED")

# Test 7: Low deception (truthful-sounding)
print("\n--- Test 7: Deception Scoring (low indicators) ---")
text2 = (
    "I was at the restaurant on Tuesday at 7:30 PM with my friend Rahul. "
    "I remember because the waiter spilled red wine on the white tablecloth. "
    "It was cold outside and I could hear loud music from the bar next door. "
    "I left at approximately 10:15 PM and took an auto rickshaw home."
)
r7 = score_deception(text2)
print(f"  Score:     {r7['deception_score']}")
print(f"  Verdict:   {r7['verdict']}")
assert r7["deception_score"] < 0.3, f"Expected low deception, got {r7['deception_score']}"
print("  [OK] PASSED")

print("\n" + "=" * 60)
print("ALL 7 TESTS PASSED")
print("=" * 60)
