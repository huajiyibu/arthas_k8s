"""多进程诊断的单元测试：_run_all_processes 每进程循环 + 注册表回退。"""
from unittest import mock

from diagnose import _run_all_processes
from injector import ARTHAS_PROCESS_REGISTRY, get_attached_processes


def _clean_registry():
    ARTHAS_PROCESS_REGISTRY.clear()


def test_run_all_processes_loops_each_process():
    """Pod 里有 2 个 JVM -> 每个都测一遍，结果各 1 条，一个不漏"""
    _clean_registry()
    procs = [
        {"pid": "111", "process": "com.example.demo.DemoApplication", "port": 3658},
        {"pid": "222", "process": "/app/sidecar-agent.jar", "port": 3659},
    ]
    with mock.patch("diagnose.get_attached_processes", return_value=procs), \
         mock.patch("diagnose.run_arthas_command",
                    return_value="result=@String[/slow] ... 捕获到数据"):
        out = _run_all_processes("pod-x", "watch ...")
    assert len(out) == 2
    assert out[0]["port"] == 3658 and out[0]["matched"] is True
    assert out[1]["port"] == 3659 and out[1]["matched"] is True


def test_run_all_processes_no_match_friendly():
    """没有捕获到数据 -> matched=False 且返回友好提示（不是报错）"""
    _clean_registry()
    procs = [{"pid": "111", "process": "app", "port": 3658}]
    with mock.patch("diagnose.get_attached_processes", return_value=procs), \
         mock.patch("diagnose.run_arthas_command",
                    return_value="Affect(class) ... 没有任何调用"):
        out = _run_all_processes("pod-x", "watch ...")
    assert out[0]["matched"] is False
    assert out[0]["result"] == "无匹配耗时请求"


def test_get_attached_processes_fallback_default():
    """注册表没有记录时回退默认端口 3658（不影响老流程/服务重启后）"""
    _clean_registry()
    procs = get_attached_processes("default", "whatever-pod")
    assert len(procs) == 1
    assert procs[0]["port"] == 3658
