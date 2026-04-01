"""
リストアップのバックグラウンド実行状態を保持するモジュール。

app.py は Streamlit により毎回再実行されるが、import されたモジュールは
Python の sys.modules キャッシュにより1回しか実行されない。
そのため、このモジュールの STATE dict はサーバープロセスが生きている限り
Streamlit の rerun をまたいで値を保持し続ける。
"""

STATE: dict = {
    "proc":        None,   # subprocess.Popen オブジェクト
    "lines":       [],     # stdout バッファ
    "running":     False,  # 実行中フラグ
    "done":        False,  # 完了フラグ
    "return_code": None,   # 終了コード
}
