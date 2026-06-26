"""Tests for AstCapabilityAnalyzer — import, call-site, and decorator detection."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.capability_analyzer.ast_capability_analyzer import (
    AstCapabilityAnalyzer,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.enums.agent_capability import AgentCapability
from awcp_instrumentation.domain.enums.hook_category import HookCategory


def _agent(source: str) -> AgentSource:
    return AgentSource.from_string(source)


def _analyze(source: str):
    return AstCapabilityAnalyzer().analyze(_agent(source))


# ---------------------------------------------------------------------------
# LLM detection
# ---------------------------------------------------------------------------

class TestLlmDetection:
    def test_openai_import(self):
        result = _analyze("import openai")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_anthropic_import(self):
        result = _analyze("import anthropic")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_langchain_import(self):
        result = _analyze("from langchain.chat_models import ChatOpenAI")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_langchain_openai_import(self):
        result = _analyze("from langchain_openai import ChatOpenAI")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_litellm_import(self):
        result = _analyze("import litellm")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_transformers_import(self):
        result = _analyze("from transformers import pipeline")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_llm_call_invoke(self):
        result = _analyze("llm.invoke(messages)")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_llm_call_create(self):
        result = _analyze("client.chat.completions.create(model='gpt-4', messages=[])")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_llm_call_generate_content(self):
        result = _analyze("model.generate_content('hello')")
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_llm_decorator(self):
        result = _analyze(
            "from somewhere import llm_call\n\n@llm_call\ndef ask(): pass"
        )
        assert AgentCapability.LLM_AGENT in result.capabilities

    def test_evidence_contains_import_signal(self):
        result = _analyze("import openai")
        ev = result.evidence.get(AgentCapability.LLM_AGENT, [])
        assert any("import:openai" in e for e in ev)

    def test_evidence_contains_call_signal(self):
        result = _analyze("llm.invoke(messages)")
        ev = result.evidence.get(AgentCapability.LLM_AGENT, [])
        assert any("call:invoke" in e for e in ev)

    def test_no_llm_for_plain_source(self):
        result = _analyze("x = 1 + 2")
        assert AgentCapability.LLM_AGENT not in result.capabilities


# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------

class TestToolDetection:
    def test_mcp_import(self):
        result = _analyze("import mcp")
        assert AgentCapability.TOOL_AGENT in result.capabilities

    def test_langchain_tools_import(self):
        result = _analyze("from langchain.tools import BaseTool")
        assert AgentCapability.TOOL_AGENT in result.capabilities

    def test_execute_tool_call(self):
        result = _analyze("execute_tool(name='search', args={})")
        assert AgentCapability.TOOL_AGENT in result.capabilities

    def test_tool_call_function(self):
        result = _analyze("result = call_tool('calculator', args)")
        assert AgentCapability.TOOL_AGENT in result.capabilities

    def test_tool_decorator(self):
        result = _analyze(
            "from langchain.tools import tool\n\n@tool\ndef my_tool(x): return x"
        )
        assert AgentCapability.TOOL_AGENT in result.capabilities

    def test_no_tool_for_pure_llm_agent(self):
        result = _analyze("import openai\nresponse = openai.chat.completions.create()")
        assert AgentCapability.TOOL_AGENT not in result.capabilities

    def test_evidence_contains_tool_signal(self):
        result = _analyze("execute_tool('search')")
        ev = result.evidence.get(AgentCapability.TOOL_AGENT, [])
        assert any("call:execute_tool" in e for e in ev)


# ---------------------------------------------------------------------------
# Search detection
# ---------------------------------------------------------------------------

class TestSearchDetection:
    def test_tavily_import(self):
        result = _analyze("from tavily import TavilyClient")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_chromadb_import(self):
        result = _analyze("import chromadb")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_pinecone_import(self):
        result = _analyze("import pinecone")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_langchain_vectorstores_import(self):
        result = _analyze("from langchain.vectorstores import FAISS")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_similarity_search_call(self):
        result = _analyze("docs = vectorstore.similarity_search(query)")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_web_search_call(self):
        result = _analyze("results = web_search(query='AI news')")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_search_call(self):
        result = _analyze("hits = client.search(index='docs', query='foo')")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_retrieve_call(self):
        result = _analyze("chunks = retriever.retrieve(question)")
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_no_search_for_pure_llm_agent(self):
        result = _analyze("import anthropic\nclient = anthropic.Anthropic()")
        assert AgentCapability.SEARCH_AGENT not in result.capabilities


# ---------------------------------------------------------------------------
# Synthesis detection
# ---------------------------------------------------------------------------

class TestSynthesisDetection:
    def test_synthesize_call(self):
        result = _analyze("answer = synthesize(docs, question)")
        assert AgentCapability.SYNTHESIS_AGENT in result.capabilities

    def test_summarize_call(self):
        result = _analyze("summary = summarize(text)")
        assert AgentCapability.SYNTHESIS_AGENT in result.capabilities

    def test_generate_answer_call(self):
        result = _analyze("resp = generate_answer(context, query)")
        assert AgentCapability.SYNTHESIS_AGENT in result.capabilities

    def test_final_response_call(self):
        result = _analyze("return final_response(merged)")
        assert AgentCapability.SYNTHESIS_AGENT in result.capabilities

    def test_langchain_chains_import(self):
        result = _analyze("from langchain.chains import LLMChain")
        assert AgentCapability.SYNTHESIS_AGENT in result.capabilities

    def test_synthesizer_decorator(self):
        result = _analyze(
            "@synthesizer\ndef combine(docs): return ' '.join(docs)"
        )
        assert AgentCapability.SYNTHESIS_AGENT in result.capabilities

    def test_no_synthesis_for_plain_search_agent(self):
        result = _analyze("import tavily")
        assert AgentCapability.SYNTHESIS_AGENT not in result.capabilities


# ---------------------------------------------------------------------------
# Required hook categories
# ---------------------------------------------------------------------------

class TestRequiredHookCategories:
    def test_pure_llm_agent_requires_llm_hooks(self):
        result = _analyze("import openai")
        req = result.required_hook_categories
        assert HookCategory.LLM_CALL in req
        assert HookCategory.TOKEN_USAGE in req
        assert HookCategory.BUDGET_WARN in req
        assert HookCategory.BUDGET_EXHAUSTED in req
        assert HookCategory.TOOL_CALL not in req

    def test_tool_agent_requires_tool_call(self):
        result = _analyze("from langchain.tools import tool\n@tool\ndef f(): pass")
        assert HookCategory.TOOL_CALL in result.required_hook_categories

    def test_search_agent_requires_web_search(self):
        result = _analyze("import chromadb")
        assert HookCategory.WEB_SEARCH in result.required_hook_categories

    def test_synthesis_agent_requires_synthesize(self):
        result = _analyze("answer = synthesize(docs, q)")
        assert HookCategory.SYNTHESIZE in result.required_hook_categories

    def test_all_required_when_no_capabilities_detected(self):
        result = _analyze("x = 42")
        assert result.required_hook_categories == frozenset(HookCategory)

    def test_task_hooks_always_present(self):
        for src in ["import openai", "execute_tool('x')", "import chromadb", "x = 1"]:
            result = _analyze(src)
            assert HookCategory.TASK_STARTED in result.required_hook_categories
            assert HookCategory.TASK_COMPLETED in result.required_hook_categories
            assert HookCategory.TASK_FAILED in result.required_hook_categories


# ---------------------------------------------------------------------------
# Syntax error handling
# ---------------------------------------------------------------------------

class TestSyntaxErrorHandling:
    def test_syntax_error_returns_all_hooks(self):
        bad_source = "def broken(:\n    pass"
        agent = AgentSource.from_string(bad_source)
        result = AstCapabilityAnalyzer().analyze(agent)
        assert result.capabilities == frozenset()
        assert result.required_hook_categories == frozenset(HookCategory)

    def test_syntax_error_empty_evidence(self):
        agent = AgentSource.from_string("def :(")
        result = AstCapabilityAnalyzer().analyze(agent)
        assert result.evidence == {}


# ---------------------------------------------------------------------------
# Multiple capabilities
# ---------------------------------------------------------------------------

class TestMultipleCapabilities:
    def test_rag_agent_llm_plus_search(self):
        source = "import openai\nimport chromadb\ndocs = vectorstore.similarity_search(q)"
        result = _analyze(source)
        assert AgentCapability.LLM_AGENT in result.capabilities
        assert AgentCapability.SEARCH_AGENT in result.capabilities

    def test_full_pipeline_agent_all_capabilities(self):
        source = (
            "import openai\n"                           # LLM_AGENT
            "from langchain.tools import tool\n"        # TOOL_AGENT
            "import chromadb\n"                         # SEARCH_AGENT
            "import opentelemetry\n"                    # OBSERVABLE_AGENT
            "import casbin\n"                           # POLICY_AGENT
            "import launchdarkly\n"                     # FEATURE_FLAG_AGENT
            "import tenacity\n"                         # RECOVERY_AGENT
            "answer = synthesize(docs, q)\n"            # SYNTHESIS_AGENT
            "request_approval(action, risk)\n"          # APPROVAL_AGENT
            "degrade(from_mode, to_mode, reason)\n"     # DEGRADATION_AGENT
        )
        result = _analyze(source)
        assert result.capabilities == frozenset(AgentCapability)
        assert result.required_hook_categories == frozenset(HookCategory)

    def test_capability_names_sorted(self):
        source = "import openai\nimport chromadb"
        result = _analyze(source)
        names = result.capability_names
        assert names == sorted(names)

    def test_required_hook_names_sorted(self):
        source = "import openai"
        result = _analyze(source)
        names = result.required_hook_names
        assert names == sorted(names)
