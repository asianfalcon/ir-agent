"""
Compatibility entrypoint for the old AceCamp minutes importer.

New code should use:
    python -m ira.connectors.acecamp.expert_processor
"""
from ira.connectors.acecamp.expert_processor import batch_process, process_article, strip_html


if __name__ == "__main__":
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else ""
    n = batch_process(ticker)
    print(f"\n完成：共存入 {n} chunks")
