import pytest


def test_get_provider_returns_groq():
    """get_provider returns GroqProvider when llm_provider='groq' and key is set."""
    from app.config import Settings
    from app.services.llm import get_provider
    from app.services.groq import GroqProvider

    settings = Settings(llm_provider="groq", groq_api_key="test-groq-key")
    provider = get_provider(settings)
    assert isinstance(provider, GroqProvider)


def test_get_provider_returns_claude():
    """get_provider returns ClaudeProvider when llm_provider='claude' and key is set."""
    from app.config import Settings
    from app.services.llm import get_provider
    from app.services.claude import ClaudeProvider

    settings = Settings(llm_provider="claude", anthropic_api_key="test-claude-key")
    provider = get_provider(settings)
    assert isinstance(provider, ClaudeProvider)


def test_get_provider_groq_missing_key():
    """get_provider raises ReviewPipelineError when groq_api_key is empty."""
    from app.config import Settings
    from app.services.llm import get_provider, ReviewPipelineError

    settings = Settings(llm_provider="groq", groq_api_key="")
    with pytest.raises(ReviewPipelineError, match="GROQ_API_KEY"):
        get_provider(settings)


def test_get_provider_claude_missing_key():
    """get_provider raises ReviewPipelineError when anthropic_api_key is empty."""
    from app.config import Settings
    from app.services.llm import get_provider, ReviewPipelineError

    settings = Settings(llm_provider="claude", anthropic_api_key="")
    with pytest.raises(ReviewPipelineError, match="ANTHROPIC_API_KEY"):
        get_provider(settings)


def test_get_provider_unknown_provider():
    """get_provider raises ValueError for unknown provider string."""
    from app.config import Settings
    from app.services.llm import get_provider

    settings = Settings(llm_provider="unknown")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_provider(settings)
