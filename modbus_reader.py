"""Modbus reader for KRON CH30 with auto-detection and register scanning."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pymodbus.client import ModbusSerialClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from serial.tools import list_ports


DEFAULT_REGISTER_MAP = {
    "settings": {
        "baudrate": 9600,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 2,
        "timeout": 1.5,
        "scan_slave_ids": [1, 2, 3, 4],
    },
    "channels": [
        {
            "name": "CH30 canal 1",
            "slave_id": 1,
            "detection": {
                "fn": 3,
                "register": 0,
                "count": 2,
                "type": "string",
                "expected_prefix": "CH30",
            },
        }
    ],
    "measurements": [
        {
            "name": "tensao_l1",
            "fn": 4,
            "register": 0,
            "count": 2,
            "type": "float",
            "unit": "V",
            "description": "Tensão fase-neutro L1",
            "ai": False,
        },
        {
            "name": "tensao_l2",
            "fn": 4,
            "register": 2,
            "count": 2,
            "type": "float",
            "unit": "V",
            "description": "Tensão fase-neutro L2",
            "ai": False,
        },
        {
            "name": "tensao_l3",
            "fn": 4,
            "register": 4,
            "count": 2,
            "type": "float",
            "unit": "V",
            "description": "Tensão fase-neutro L3",
            "ai": False,
        },
        {
            "name": "tensao_ll_l1",
            "fn": 4,
            "register": 6,
            "count": 2,
            "type": "float",
            "unit": "V",
            "description": "Tensão linha-linha R-S",
            "ai": True,
        },
        {
            "name": "tensao_ll_l2",
            "fn": 4,
            "register": 8,
            "count": 2,
            "type": "float",
            "unit": "V",
            "description": "Tensão linha-linha S-T",
            "ai": True,
        },
        {
            "name": "tensao_ll_l3",
            "fn": 4,
            "register": 10,
            "count": 2,
            "type": "float",
            "unit": "V",
            "description": "Tensão linha-linha T-R",
            "ai": True,
        },
        {
            "name": "potencia_kw_inst",
            "fn": 4,
            "register": 20,
            "count": 2,
            "type": "float",
            "unit": "kW",
            "description": "Potência ativa instantânea",
            "ai": True,
        },
        {
            "name": "energia_kwh_a",
            "fn": 4,
            "register": 40,
            "count": 2,
            "type": "float",
            "unit": "kWh",
            "description": "Energia canal A acumulada",
            "ai": True,
        },
        {
            "name": "energia_kwh_b",
            "fn": 4,
            "register": 42,
            "count": 2,
            "type": "float",
            "unit": "kWh",
            "description": "Energia canal B acumulada",
            "ai": False,
        },
        {
            "name": "frequencia",
            "fn": 4,
            "register": 60,
            "count": 2,
            "type": "float",
            "unit": "Hz",
            "description": "Frequência",
            "ai": True,
        },
        {
            "name": "fp_avg",
            "fn": 4,
            "register": 70,
            "count": 2,
            "type": "float",
            "unit": "pu",
            "description": "Fator de potência médio",
            "ai": True,
        },
    ],
}


@dataclass
class DetectionResult:
    port: str
    slave_id: int
    channel_name: str
    raw_identifier: Optional[str] = None


class KronReader:
    """Reader that auto-detects KRON CH30 devices on serial ports."""

    def __init__(self, base_path: Path | str):
        base = Path(base_path)
        cfg_path = base / "registers_kron03_real.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as fh:
                self.map = json.load(fh)
        else:
            self.map = DEFAULT_REGISTER_MAP
        self.settings = self.map.get("settings", {})
        self.channels = self.map.get("channels", [])
        self.measurements = self.map.get("measurements", [])
        self.client: Optional[ModbusSerialClient] = None
        self.current_slave_id: Optional[int] = None
        self.channel_name: Optional[str] = None
        self.connection_info: Dict[str, Optional[str]] = {
            "status": "desconectado",
            "port": None,
            "canal": None,
            "identificador": None,
        }
        self.last_scan: List[Dict] = []

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        forced_port = os.getenv("MODBUS_PORT")
        forced_slave = os.getenv("MODBUS_SLAVE_ID")
        if forced_port:
            slave = int(forced_slave) if forced_slave else self._default_slave()
            detection = DetectionResult(port=forced_port, slave_id=slave, channel_name=f"CH30 slave {slave}")
        else:
            detection = self._auto_detect()
        if not detection:
            raise RuntimeError("Não foi possível detectar o equipamento CH30 em nenhuma porta COM disponível.")

        print(
            f"[Modbus] Detectado {detection.channel_name} na porta {detection.port}"
            + (f" (id: {detection.raw_identifier})" if detection.raw_identifier else "")
        )

        client = ModbusSerialClient(
            method="rtu",
            port=detection.port,
            baudrate=self.settings.get("baudrate", 9600),
            bytesize=self.settings.get("bytesize", 8),
            parity=self.settings.get("parity", "N"),
            stopbits=self.settings.get("stopbits", 2),
            timeout=self.settings.get("timeout", 1.5),
        )
        if not client.connect():
            raise RuntimeError(f"Falha ao abrir a porta {detection.port}.")

        # test read
        self.client = client
        self.current_slave_id = detection.slave_id
        self.channel_name = detection.channel_name
        if not self._test_connection():
            client.close()
            self.client = None
            raise RuntimeError("Teste de conexão Modbus falhou.")

        self.connection_info = {
            "status": "conectado",
            "port": detection.port,
            "canal": detection.channel_name,
            "identificador": detection.raw_identifier,
        }
        self.last_scan = self.scan_registers()
        return True

    def _default_slave(self) -> int:
        scan = self.settings.get("scan_slave_ids") or [1]
        return int(scan[0])

    def _auto_detect(self) -> Optional[DetectionResult]:
        ports = list(list_ports.comports())
        if not ports:
            raise RuntimeError("Nenhuma porta serial encontrada para tentativa de detecção.")

        for port in ports:
            for channel in self._channels_to_scan():
                result = self._probe_channel(port.device, channel)
                if result:
                    return result
        return None

    def _channels_to_scan(self) -> Iterable[Dict]:
        if self.channels:
            return self.channels
        # fallback: create channels from scan_slave_ids list
        ids = self.settings.get("scan_slave_ids") or [1]
        return (
            {"name": f"CH30 canal {sid}", "slave_id": sid, "detection": {"fn": 3, "register": 0, "count": 1}}
            for sid in ids
        )

    def _probe_channel(self, port: str, channel_cfg: Dict) -> Optional[DetectionResult]:
        slave_id = int(channel_cfg.get("slave_id", self._default_slave()))
        det_cfg = channel_cfg.get("detection", {})
        fn = int(det_cfg.get("fn", 3))
        address = int(det_cfg.get("register", 0))
        count = int(det_cfg.get("count", 1))
        dtype = det_cfg.get("type", "uint16")
        expected = det_cfg.get("expected_prefix")

        client = ModbusSerialClient(
            method="rtu",
            port=port,
            baudrate=self.settings.get("baudrate", 9600),
            bytesize=self.settings.get("bytesize", 8),
            parity=self.settings.get("parity", "N"),
            stopbits=self.settings.get("stopbits", 2),
            timeout=self.settings.get("timeout", 1.5),
        )
        if not client.connect():
            return None

        try:
            if fn == 4:
                response = client.read_input_registers(address=address, count=count, slave=slave_id)
            else:
                response = client.read_holding_registers(address=address, count=count, slave=slave_id)
            if not response or response.isError():
                return None
            raw_value = self._decode_registers(response.registers, dtype=dtype)
            if isinstance(raw_value, str):
                identifier = raw_value.strip()
            else:
                identifier = str(raw_value)
            if expected and identifier:
                if not identifier.upper().startswith(str(expected).upper()):
                    return None
            channel_name = channel_cfg.get("name") or f"CH30 canal {slave_id}"
            return DetectionResult(port=port, slave_id=slave_id, channel_name=channel_name, raw_identifier=identifier)
        finally:
            client.close()

    def _test_connection(self) -> bool:
        if not self.client:
            return False
        try:
            test_entry = next((m for m in self.measurements if m.get("ai")), None) or (self.measurements[0] if self.measurements else None)
        except IndexError:
            test_entry = None
        if not test_entry:
            return True
        try:
            self._read_measurement(test_entry)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Reading helpers
    # ------------------------------------------------------------------
    def _decode_registers(
        self,
        registers: List[int],
        *,
        dtype: str,
        scale: float | int | None = None,
        byteorder: str | None = None,
        wordorder: str | None = None,
    ):
        scale = scale if scale is not None else 1.0
        byteorder = (byteorder or "big").lower()
        wordorder = (wordorder or "big").lower()
        byte = Endian.Big if byteorder.startswith("b") else Endian.Little
        word = Endian.Big if wordorder.startswith("b") else Endian.Little
        if wordorder in {"dcba", "cdab", "badc"}:
            # handle common Modbus float arrangements
            mapping = {
                "dcba": (Endian.Little, Endian.Little),
                "cdab": (Endian.Big, Endian.Little),
                "badc": (Endian.Little, Endian.Big),
            }
            word, byte = mapping[wordorder]
        decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=byte, wordorder=word)
        dtype = dtype.lower()
        if dtype in {"float", "float32"}:
            value = decoder.decode_32bit_float()
        elif dtype in {"uint32", "u32"}:
            value = decoder.decode_32bit_uint()
        elif dtype in {"int32", "i32"}:
            value = decoder.decode_32bit_int()
        elif dtype in {"uint16", "u16"}:
            value = registers[0]
        elif dtype in {"int16", "i16"}:
            value = decoder.decode_16bit_int()
        elif dtype == "string":
            raw = decoder.decode_string(size=len(registers) * 2)
            value = raw.decode("latin-1", errors="ignore").strip().strip("\x00")
        else:
            value = registers[0]
        if isinstance(value, (int, float)):
            return value * float(scale)
        return value

    def _read_measurement(self, entry: Dict):
        if not self.client:
            raise RuntimeError("Cliente Modbus não conectado")
        fn = int(entry.get("fn", 3))
        address = int(entry.get("register", 0))
        count = int(entry.get("count", 1))
        dtype = entry.get("type", "uint16")
        scale = entry.get("scale")
        byteorder = entry.get("byteorder")
        wordorder = entry.get("wordorder") or entry.get("endian")

        if fn == 4:
            response = self.client.read_input_registers(address=address, count=count, slave=self.current_slave_id)
        else:
            response = self.client.read_holding_registers(address=address, count=count, slave=self.current_slave_id)
        if not response or response.isError():
            raise RuntimeError(f"Falha ao ler registrador {address} (fn={fn}).")
        return self._decode_registers(response.registers, dtype=dtype, scale=scale, byteorder=byteorder, wordorder=wordorder)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def read_all(self) -> Dict[str, Optional[float]]:
        snapshot: Dict[str, Optional[float]] = {}
        if not self.client:
            return snapshot
        for entry in self.measurements:
            name = entry.get("name")
            if not name:
                continue
            try:
                snapshot[name] = self._read_measurement(entry)
            except Exception:
                snapshot[name] = None
        return snapshot

    def scan_registers(self) -> List[Dict]:
        if not self.client:
            return []
        snapshot = []
        for entry in self.measurements:
            row = {k: entry.get(k) for k in ("name", "register", "fn", "unit", "description", "ai")}
            try:
                row["value"] = self._read_measurement(entry)
            except Exception:
                row["value"] = None
            snapshot.append(row)
        self.last_scan = snapshot
        return snapshot

    def get_register_metadata(self) -> List[Dict]:
        meta = []
        for entry in self.measurements:
            meta.append(
                {
                    "name": entry.get("name"),
                    "register": entry.get("register"),
                    "fn": entry.get("fn", 3),
                    "unit": entry.get("unit"),
                    "description": entry.get("description"),
                    "ai": entry.get("ai", False),
                }
            )
        return meta

    def relevant_field_names(self) -> List[str]:
        names = [m.get("name") for m in self.measurements if m.get("ai")]
        return [n for n in names if n]

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.connection_info = {
                "status": "desconectado",
                "port": None,
                "canal": None,
                "identificador": None,
            }


__all__ = ["KronReader"]
