"""Pydantic modellerinden TypeScript tipleri üretir.

    python scripts/export_schema.py

Sözleşme tek yerde (``schemas/messages.py``) tanımlıdır; arayüzün tipleri
elle yazılmaz, buradan üretilir. Sözleşmeyi değiştiren kişi bu betiği
çalıştırıp çıktıyı aynı PR içinde gönderir.

Üretilen dosya:
    frontend/src/types/messages.generated.ts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gaze_aac.schemas import messages as m  # noqa: E402

OUT_TS = ROOT.parent / "frontend" / "src" / "types" / "messages.generated.ts"
OUT_JSON = ROOT.parent / "docs" / "ws-schema.json"

CLIENT_MODELS = [
    m.ClientHello,
    m.ClientGazeSample,
    m.ClientCalibrationSample,
    m.ClientCalibrationFit,
    m.ClientTargets,
    m.ClientSelect,
    m.ClientExpand,
    m.ClientSpeak,
    m.ClientStudyStart,
    m.ClientTrialStart,
    m.ClientTrialEnd,
    m.ClientStudyEnd,
]
SERVER_MODELS = [
    m.ServerReady,
    m.ServerGaze,
    m.ServerDwellProgress,
    m.ServerSelection,
    m.ServerCalibrationResult,
    m.ServerCandidates,
    m.ServerStudyPlan,
    m.ServerError,
]

_PRIMITIVES = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
}


def ts_type(schema: dict, defs: dict) -> str:
    """JSON Schema parçasını TypeScript tipine çevirir."""
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]

    if "anyOf" in schema:
        parts = [ts_type(s, defs) for s in schema["anyOf"]]
        return " | ".join(dict.fromkeys(parts))

    if "const" in schema:
        return f'"{schema["const"]}"'

    kind = schema.get("type")
    if kind == "array":
        return f"{ts_type(schema.get('items', {}), defs)}[]"
    if kind == "null":
        return "null"
    if kind == "object":
        return "Record<string, unknown>"
    return _PRIMITIVES.get(str(kind), "unknown")


def render_interface(name: str, schema: dict, defs: dict) -> str:
    lines = [f"export interface {name} {{"]
    required = set(schema.get("required", []))
    for field_name, field_schema in schema.get("properties", {}).items():
        optional = "" if field_name in required else "?"
        description = field_schema.get("description")
        if description:
            lines.append(f"  /** {description} */")
        lines.append(f"  {field_name}{optional}: {ts_type(field_schema, defs)};")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    collected: dict[str, dict] = {}
    shared: dict[str, dict] = {}

    for model in CLIENT_MODELS + SERVER_MODELS:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        shared.update(schema.pop("$defs", {}))
        collected[model.__name__] = schema

    blocks = [
        "// BU DOSYA ÜRETİLMİŞTİR — ELLE DÜZENLEMEYİN.",
        "// Kaynak: backend/src/gaze_aac/schemas/messages.py",
        "// Yeniden üretmek için: python backend/scripts/export_schema.py",
        "",
    ]

    for name, schema in sorted(shared.items()):
        blocks.append(render_interface(name, schema, shared))
        blocks.append("")

    for name, schema in collected.items():
        blocks.append(render_interface(name, schema, shared))
        blocks.append("")

    separator = "\n  | "
    client_union = separator.join(model.__name__ for model in CLIENT_MODELS)
    server_union = separator.join(model.__name__ for model in SERVER_MODELS)
    blocks.append("export type ClientMessage =\n  | " + client_union + ";")
    blocks.append("")
    blocks.append("export type ServerMessage =\n  | " + server_union + ";")
    blocks.append("")

    OUT_TS.parent.mkdir(parents=True, exist_ok=True)
    OUT_TS.write_text("\n".join(blocks), encoding="utf-8")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"$defs": shared, "messages": collected}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"TypeScript tipleri yazıldı: {OUT_TS}")
    print(f"JSON şeması yazıldı: {OUT_JSON}")


if __name__ == "__main__":
    main()
