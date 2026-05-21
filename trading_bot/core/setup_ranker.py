"""
core/setup_ranker.py — Institutional-Grade Expected Value Setup Prioritisation
=============================================================================
Ranks candidate trade setups based on their mathematical Expected Value (EV).
Ensures resource capacity bounds (Config.MAX_CONCURRENT_TRADES) are strictly
allocated to the highest-expectancy setups.

Expected Value Formula:
    EV = P_cal * RR - (1 - P_cal)
    where:
        P_cal = Calibrated win probability [0.0, 1.0]
        RR    = Reward-to-Risk ratio (e.g. 2.0)
"""

from config import Config


class SetupRanker:
    """
    Ranks and filters simultaneous or sequential trade setup candidates
    by their Expected Value (EV) and technical quality score.
    """

    @classmethod
    def calculate_expected_value(cls, p_cal: float, rr: float) -> float:
        """
        Computes the expected value of a trade given its calibrated success probability
        and reward-to-risk ratio.
        
        Parameters
        ----------
        p_cal : calibrated probability of success (between 0.0 and 1.0, or 0 and 100)
        rr    : reward-to-risk ratio (e.g. 2.0)
        """
        # Ensure p_cal is normalized between 0.0 and 1.0
        p = p_cal / 100.0 if p_cal > 1.0 else p_cal
        p = max(0.0, min(1.0, p))
        
        q = 1.0 - p
        ev = (p * rr) - q
        return float(ev)

    @classmethod
    def rank_candidates(cls, candidates: list[dict], available_slots: int = None) -> list[dict]:
        """
        Ranks candidate setups based on Expected Value (EV) and Setup Quality,
        filtering for positive EV and returning the top candidates within available slots.
        
        Parameters
        ----------
        candidates      : list of dictionaries representing setup candidates
        available_slots : max number of trades we can open (None = Config.MAX_CONCURRENT_TRADES)
        
        Each candidate dictionary should contain:
            - "side": "BUY" or "SELL"
            - "ai_prob" or "p_cal": calibrated win probability (0-100 or 0-1)
            - "current_rr" or "rr_ratio" or "rr": reward-to-risk ratio
            - "setup_quality": technical quality score (0-100)
        """
        if not candidates:
            return []

        if available_slots is None:
            available_slots = Config.MAX_CONCURRENT_TRADES

        ranked_list = []
        for c in candidates:
            # Resolve calibrated probability
            p_val = c.get("p_cal", c.get("ai_prob", 50.0))
            
            # Resolve RR ratio
            rr_val = c.get("current_rr", c.get("rr_ratio", c.get("rr", 2.0)))
            
            # Calculate EV
            ev = cls.calculate_expected_value(p_val, rr_val)
            
            # Create a copy with EV injected
            c_copy = c.copy()
            c_copy["expected_value"] = ev
            ranked_list.append(c_copy)

        # Sort: Primary by Expected Value (descending), Secondary by Setup Quality (descending)
        ranked_list.sort(
            key=lambda x: (x.get("expected_value", -999.0), x.get("setup_quality", 0.0)),
            reverse=True
        )

        # Filter: keep only positive EV setups (or baseline zero)
        # Note: In institutional systems, trading negative or neutral EV is mathematically sub-optimal.
        positive_ev_candidates = [c for c in ranked_list if c.get("expected_value", -1.0) > 0.0]

        # Return only the top setups that fit within available concurrent slots
        return positive_ev_candidates[:max(0, available_slots)]
