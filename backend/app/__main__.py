"""统一入口：支持 python -m backend.app。"""

from backend.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
