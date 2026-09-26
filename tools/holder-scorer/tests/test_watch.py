from holder_scorer.watch import accept_launch


def test_accept_launch_filters_pools_and_types():
    mint = "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"
    assert accept_launch({"mint": mint}) == (True, "")
    assert accept_launch({"mint": mint, "txType": "create", "pool": "pump"})[0]
    assert not accept_launch({"mint": mint, "pool": "bonk"})[0]
    assert not accept_launch({"mint": mint, "txType": "buy"})[0]
    assert not accept_launch({"mint": 5})[0]
    assert not accept_launch({"message": "Successfully subscribed"})[0]
