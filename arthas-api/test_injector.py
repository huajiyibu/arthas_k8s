"""injector.py 纯逻辑的单元测试（_parse_jps：jps -l 输出解析）。

验证"Pod 内多 Java 进程一个不漏"的核心解析逻辑，不需要连真实集群。
"""
from injector import _parse_jps


def test_parse_jps_all_processes_kept():
    """多 Java 进程：全部保留，一个都不漏"""
    output = "1234 com.example.demo.DemoApplication\n" \
             "5678 /app/sidecar-agent.jar\n" \
             "9999 sun.tools.jps.Jps\n"
    assert _parse_jps(output) == [
        ("1234", "com.example.demo.DemoApplication"),
        ("5678", "/app/sidecar-agent.jar"),
        ("9999", "sun.tools.jps.Jps"),
    ]


def test_parse_jps_ignores_junk_lines():
    """警告/报错/空行/无空格行都应忽略"""
    output = "Warning: not a real warning\n" \
             "jps: command not found\n" \
             "\n" \
             "1234 com.example.demo.DemoApplication\n" \
             "no-pid-line\n"
    assert _parse_jps(output) == [("1234", "com.example.demo.DemoApplication")]


def test_parse_jps_empty_returns_empty_list():
    """没有任何合法 Java 进程行 -> 空列表（上层据此报"没有 Java 进程"）"""
    assert _parse_jps("") == []
    assert _parse_jps("hello world\nfoo bar baz\n") == []
