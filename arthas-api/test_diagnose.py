r"""diagnose.py 中正则解析函数的单元测试（pytest）。

运行：在 arthas-api 目录下执行
    ..\.venv\Scripts\python.exe -m pytest test_diagnose.py -v
"""
from diagnose import has_match, extract_uris, filter_match_method


# ============ 公共样例数据（基于真实 Arthas 输出） ============

# 慢接口查询 watch 输出（含 result=）
WATCH_SLOW = """[arthas@1]$ watch org.apache.catalina.core.ApplicationFilterChain doFilter '{params[0].getRequestURI(), params[1].getStatus()}' -x 2 '#cost>1000' -n 5 | plaintext
Press Q or Ctrl+C to abort.
Affect(class count: 1 , method count: 1) cost in 120 ms, listenerId: 7
method=org.apache.catalina.core.ApplicationFilterChain.doFilter location=AtExit
ts=2026-08-04 08:29:02.784; [cost=2032.050998ms] result=@ArrayList[
    @String[/slow],
    @Integer[200],
]
"""

# 方法栈追踪输出（含 `---[ 调用栈）
TRACE_SLOW = """[arthas@1]$ trace com.example.demo.DemoController slow -n 5 '#cost>0' --skipJDKMethod false | plaintext
Press Q or Ctrl+C to abort.
Affect(class count: 1 , method count: 1) cost in 79 ms, listenerId: 3
`---ts=2026-08-04 08:30:16.156;thread_name=http-nio-8080-exec-7;id=22
    `---[2000.821784ms] com.example.demo.DemoController:slow()
        `---[99.99% 2000.61651ms ] java.lang.Thread:sleep() #21
"""

# monitor 输出（有调用数据：total=2）
MONITOR_WITH_DATA = """[arthas@1]$ monitor -c 5 com.example.demo.DemoController * | plaintext
Press Q or Ctrl+C to abort.
Affect(class count: 1 , method count: 3) cost in 59 ms, listenerId: 5
 timestamp   class              method   total  success  fail  avg-rt  fail-rat
--------------------------------------------------------------------------------
 2026-08-04  com.example.demo.  slow     2      2        0     2005.94  0.00%
--------------------------------------------------------------------------------
 2026-08-04  com.example.demo.  slow     0      0        0     0.00    0.00%
"""

# monitor 输出（无调用：total=0）
MONITOR_NO_DATA = """[arthas@1]$ monitor -c 5 com.example.demo.DemoController * | plaintext
Affect(class count: 1 , method count: 3) cost in 59 ms, listenerId: 5
 timestamp   class              method   total  success  fail  avg-rt  fail-rat
 2026-08-04  com.example.demo.  slow     0      0        0     0.00    0.00%
"""

# 只有 banner + Affect（watch 挂了但没抓到调用）
ONLY_AFFECT = """[arthas@1]$ watch org.apache.catalina.core.ApplicationFilterChain doFilter '{params[0].getRequestURI(), params[1].getStatus()}' -x 2 '#cost>1000' -n 5 | plaintext
Press Q or Ctrl+C to abort.
Affect(class count: 1 , method count: 1) cost in 120 ms, listenerId: 7
"""

# 匹配方法 watch 输出（含 /slow 和 /fast 两个结果块）
MATCH_BOTH = """[arthas@1]$ watch org.springframework.web.servlet.DispatcherServlet doDispatch '{params[0].getRequestURI(), target.getHandler(params[0])}' -n 50 | plaintext
Affect(class count: 1 , method count: 1) cost in 140 ms, listenerId: 6
method=org.springframework.web.servlet.DispatcherServlet.doDispatch location=AtExit
ts=2026-08-04 08:57:29.278; [cost=2005.07878ms] result=@ArrayList[
    @String[/slow],
    @HandlerExecutionChain[HandlerExecutionChain with [com.example.demo.DemoController#slow()] and 2 interceptors],
]
method=org.springframework.web.servlet.DispatcherServlet.doDispatch location=AtExit
ts=2026-08-04 08:57:31.350; [cost=4.538633ms] result=@ArrayList[
    @String[/fast],
    @HandlerExecutionChain[HandlerExecutionChain with [com.example.demo.DemoController#fast()] and 2 interceptors],
]
"""

# 匹配方法输出：有 URI 但没有 handler（类#方法缺失）
MATCH_NO_HANDLER = """[arthas@1]$ watch org.springframework.web.servlet.DispatcherServlet doDispatch '{params[0].getRequestURI(), target.getHandler(params[0])}' -n 50 | plaintext
Affect(class count: 1 , method count: 1) cost in 100 ms, listenerId: 9
method=org.springframework.web.servlet.DispatcherServlet.doDispatch location=AtExit
ts=2026-08-04 08:58:00.000; [cost=1.2ms] result=@ArrayList[
    @String[/unknown],
    @HandlerExecutionChain[null],
]
"""


# ============ has_match ============

def test_has_match_watch_result():
    """watch 输出含 result= 应判定为有数据"""
    assert has_match(WATCH_SLOW) is True


def test_has_match_trace_stack():
    """trace 输出含调用栈（`---[ 和 [cost=）应判定为有数据"""
    assert has_match(TRACE_SLOW) is True


def test_has_match_monitor_with_data():
    """monitor 输出有调用数据（total>0 的行）应判定为有数据（回归：曾误判为无匹配）"""
    assert has_match(MONITOR_WITH_DATA) is True


def test_has_match_monitor_no_data():
    """monitor 输出全是 total=0 应判定为无数据"""
    assert has_match(MONITOR_NO_DATA) is False


def test_has_match_only_affect():
    """只有 banner + Affect（未抓到调用）应判定为无数据"""
    assert has_match(ONLY_AFFECT) is False


def test_has_match_empty():
    """空输出应判定为无数据"""
    assert has_match("") is False


# ============ extract_uris ============

def test_extract_uris_single():
    """从慢接口 watch 输出提取 /slow"""
    assert extract_uris(WATCH_SLOW) == ["/slow"]


def test_extract_uris_multiple_dedup():
    """多 URI 提取且去重保序"""
    output = WATCH_SLOW + "ts=...; result=@ArrayList[\n    @String[/fast],\n]\n" \
             + "ts=...; result=@ArrayList[\n    @String[/slow],\n]\n"
    assert extract_uris(output) == ["/slow", "/fast"]


def test_extract_uris_none():
    """没有 URI 时返回空列表"""
    assert extract_uris(ONLY_AFFECT) == []


# ============ filter_match_method ============

def test_filter_match_slow():
    """按 /slow 匹配到 DemoController.slow"""
    assert filter_match_method(MATCH_BOTH, "/slow") == {
        "request_uri": "/slow",
        "class": "com.example.demo.DemoController",
        "method": "slow",
    }


def test_filter_match_fast():
    """按 /fast 匹配到 DemoController.fast"""
    assert filter_match_method(MATCH_BOTH, "/fast") == {
        "request_uri": "/fast",
        "class": "com.example.demo.DemoController",
        "method": "fast",
    }


def test_filter_match_uri_not_found():
    """目标 URI 不存在时返回 None"""
    assert filter_match_method(MATCH_BOTH, "/nope") is None


def test_filter_match_no_handler():
    """有 URI 但没解析到 类#方法 时返回 None"""
    assert filter_match_method(MATCH_NO_HANDLER, "/unknown") is None


def test_filter_match_empty_output():
    """空输出时返回 None"""
    assert filter_match_method("", "/slow") is None
