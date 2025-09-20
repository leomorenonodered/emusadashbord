# modbus_reader_sim.py
import math, time, random

class KronReaderSim:
    def __init__(self, base_ll=380.0, base_ln=220.0):
        self.base_ll = base_ll
        self.base_ln = base_ln
        self.t0 = time.time()
        self.kwh_a = 12345.0
        self.kwh_b = 23456.0
        self._last_ts = self.t0
        self._last_kw = 20.0

    def connect(self):
        return True

    def _wave(self, amp=1.0, speed=0.05, phase=0.0):
        t = time.time() - self.t0
        return amp * math.sin(2*math.pi*speed*t + phase)

    def _noisy(self, base, noise=0.8):
        return base + random.uniform(-noise, noise)

    def read_all(self):
        ln1 = self._noisy(self.base_ln + self._wave(2.5, 0.01, 0))
        ln2 = self._noisy(self.base_ln + self._wave(2.5, 0.01, 2*math.pi/3))
        ln3 = self._noisy(self.base_ln + self._wave(2.5, 0.01, -2*math.pi/3))

        ll1 = self._noisy(self.base_ll + self._wave(5.0, 0.01, 0))
        ll2 = self._noisy(self.base_ll + self._wave(5.0, 0.01, 2*math.pi/3))
        ll3 = self._noisy(self.base_ll + self._wave(5.0, 0.01, -2*math.pi/3))
        ll_avg = (ll1 + ll2 + ll3) / 3

        i1 = max(0.0, 8.0 + self._wave(2.0, 0.02) + random.uniform(-0.2, 0.2))
        i2 = max(0.0, 7.5 + self._wave(1.8, 0.018, 1.0) + random.uniform(-0.2, 0.2))
        i3 = max(0.0, 7.8 + self._wave(1.6, 0.017, -0.8) + random.uniform(-0.2, 0.2))

        fp = min(1.0, max(0.7, 0.95 + random.uniform(-0.02, 0.02)))

        i_avg = (i1 + i2 + i3) / 3
        kw_inst = max(0.0, (math.sqrt(3) * ll_avg * i_avg * fp) / 1000.0)
        kw_inst = 0.8*self._last_kw + 0.2*kw_inst
        self._last_kw = kw_inst

        now = time.time()
        dt_h = max(1e-6, (now - self._last_ts) / 3600.0)
        self.kwh_a += kw_inst * dt_h
        self.kwh_b += (kw_inst * 0.5) * dt_h
        self._last_ts = now

        freq = 60.0 + random.uniform(-0.05, 0.05)

        return {
            "tensao_l1": ln1, "tensao_l2": ln2, "tensao_l3": ln3,
            "tensao_ll_l1": ll1, "tensao_ll_l2": ll2, "tensao_ll_l3": ll3,
            "tensao_ll_avg": ll_avg,
            "corrente_l1": i1, "corrente_l2": i2, "corrente_l3": i3,
            "potencia_kw_inst": kw_inst,
            "energia_kwh_a": self.kwh_a, "energia_kwh_b": self.kwh_b,
            "frequencia": freq, "fp_avg": fp
        }
