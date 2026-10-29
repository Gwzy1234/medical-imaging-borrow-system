"""启动 FastAPI 开发服务器。

用法（在项目根目录执行）：
    python scripts/run_api.py
    python scripts/run_api.py --reload --port 8000
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="启动开发服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="修改代码后自动重启")
    args = parser.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
