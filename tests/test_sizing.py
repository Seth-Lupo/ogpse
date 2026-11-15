import numpy as np

from ogpse.costs import Costs
from ogpse.sizing import Design, min_pv, unserved_hours, uptime

COSTS = Costs(900.0, 350.0, 220.0, 1000.0)


def test_battery_alone_covers_exactly_its_hours():
    pv = np.zeros(48)
    assert unserved_hours(pv, Design(0, 1.0, 10), rte=1.0) == 38


def test_losses_reduce_delivered_energy():
    pv = np.zeros(48)
    assert unserved_hours(pv, Design(0, 1.0, 10), rte=0.81) == 39  # 10 MWh x 0.9 discharge efficiency


def test_charging_is_power_limited():
    pv = np.tile(np.r_[np.full(10, 1.0), np.zeros(14)], 3)  # 2 MW surplus for 10 h, then 14 h of night
    slow = unserved_hours(pv, Design(3, 1.0, 14), rte=1.0)
    fast = unserved_hours(pv, Design(3, 2.0, 14), rte=1.0)
    assert fast == 0 and slow > 0


def test_uptime_monotone_in_pv():
    pv = np.random.default_rng(0).uniform(0, 0.7, 24 * 365) * np.tile(np.r_[np.zeros(12), np.ones(12)], 365)
    ups = [uptime(pv, Design(p, 3.0, 24), 0.85) for p in np.linspace(2, 10, 9)]
    assert all(b >= a for a, b in zip(ups, ups[1:]))


def test_min_pv_meets_target():
    pv = np.random.default_rng(1).uniform(0, 0.7, 24 * 365) * np.tile(np.r_[np.zeros(12), np.ones(12)], 365)
    p = min_pv(pv, 3.0, 36, 0.85, 0.99, 1.0, 30.0, 0.005)
    assert uptime(pv, Design(p, 3.0, 36), 0.85) >= 0.99
    assert uptime(pv, Design(p * 0.97, 3.0, 36), 0.85) < 0.99
