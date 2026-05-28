#!/usr/bin/env python3
"""Testa conexão com CI&T Flow LiteLLM (mesmas variáveis do .env do app)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_app_config  # noqa: E402
from src.llm_connection_test import (  # noqa: E402
    format_connection_report,
    run_all_connection_tests,
    test_anthropic_provider,
)


def main() -> int:
    config = load_app_config()
    result = test_anthropic_provider(config)
    print("=== Teste Anthropic / Flow LiteLLM ===\n")
    print(result.detail)
    if result.reply is not None:
        print(f"\nResposta: {result.reply!r}")
    if result.success:
        print("\nSucesso.")
        return 0
    print("\nFalha. Para testar todos os provedores: use o botão na interface ou:")
    report, _ = format_connection_report(run_all_connection_tests(config))
    print("\n" + report)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
