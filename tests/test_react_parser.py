"""ReAct 解析器单元测试。

为什么独立成 pytest 文件：原单测内嵌在 .github/workflows/ci.yml 的 YAML heredoc 中，
2026-08-05 曾因编码损坏（闭合标签 '<' 丢失 + 乱码）导致 CI 连续 11 次失败。
独立成测试文件后：本地可跑、CI 引用同一文件、避免 YAML 内嵌代码的编码风险。

本地运行：python -m pytest tests/test_react_parser.py -q
"""

from finpilot.agent.react_nodes import parse_react_output


def test_standard_react_format():
    """标准 ReAct 三段式：Thought / Action / Action Input。"""
    text = 'Thought: t\nAction: nl2sql\nAction Input: {"question":"x"}\n'
    r = parse_react_output(text)
    assert r["parse_ok"] is True
    assert r["action"] == "nl2sql"


def test_tool_call_xml_format():
    """<tool_call> XML 风格（Qwen / Mistral 系）。"""
    text = '<tool_call><function=nl2sql><parameter=question>x</parameter></function></tool_call>'
    r = parse_react_output(text)
    assert r["parse_ok"] is True
    assert r["action"] == "nl2sql"


def test_answer_tag_format():
    """<answer>...</answer> 作为最终答案（含中文内容）。"""
    text = '<answer>最终答案</answer>'
    r = parse_react_output(text)
    assert r["parse_ok"] is True
    assert r["action"] == "FinalAnswer"
    assert r["final_answer"] == "最终答案"


def test_final_answer_tag_format():
    """<final_answer> 标签同样被识别为最终答案。"""
    text = '<final_answer>ok</final_answer>'
    r = parse_react_output(text)
    assert r["parse_ok"] is True
    assert r["action"] == "FinalAnswer"


def test_bare_function_format():
    """无 <tool_call> 包裹的裸 <function=NAME> 格式。"""
    text = '<function=nl2sql><parameter=question>x</parameter></function>'
    r = parse_react_output(text)
    assert r["parse_ok"] is True
    assert r["action"] == "nl2sql"


def test_unparseable_input_returns_false():
    """空输入或无结构输入必须返回 parse_ok=False（作为 retry 信号）。"""
    assert parse_react_output("")["parse_ok"] is False
    assert parse_react_output("没有可解析的结构")["parse_ok"] is False
