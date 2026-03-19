"""検索エージェントの動作テスト"""
from agents.search_agent import search_google

print("🔍 DuckDuckGo検索テスト開始...")
results = search_google("KENJA GLOBAL 株式会社", "qdr:m", num=5)

print(f"\n✅ 取得件数: {len(results)}件\n")
for i, r in enumerate(results, 1):
    print(f"[{i}] {r['title']}")
    print(f"    URL: {r['url']}")
    print(f"    概要: {r['snippet'][:80]}")
    print()
