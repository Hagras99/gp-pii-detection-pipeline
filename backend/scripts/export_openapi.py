"""Write docs/openapi.json. The frontend can generate TypeScript types from it, e.g.:
   npx openapi-typescript docs/openapi.json -o src/api-types.ts
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.mock_server import app  # noqa: E402
out = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", out)
