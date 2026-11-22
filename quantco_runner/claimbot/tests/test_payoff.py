from claimbot.evaluation.payoff import round_net, settle


def test_settle_matrix():
    t, c = 100, 400
    assert settle(100, 110, t, c) == 100      # fair, accepted
    assert settle(100, 90, t, c) == 150       # fair, wrongly rejected
    assert settle(150, 200, t, c) == 150      # inflated, accepted
    assert settle(500, 900, t, c) == 400      # inflated, accepted, capped
    assert settle(150, 110, t, c) == 0        # inflated, rejected

def test_round_matches_game_description_example():
    net = round_net({"Alpha": (100, 130), "Beta": (150, 90), "Delta": (100, 110)}, t=100, c=400)
    assert net == {"Alpha": 150, "Beta": -300, "Delta": 150}
