from app.graph import classify_fallback
from app.policies import search_policies

def test_intents():
    assert classify_fallback('I need a refund')=='refund'
    assert classify_fallback('Please cancel my order')=='cancel'
    assert classify_fallback('Where is my delivery?')=='delivery'
    assert classify_fallback('Hello')=='general'
def test_policy_retrieval():
    assert any(x['source']=='refund' for x in search_policies('refund damaged item'))
