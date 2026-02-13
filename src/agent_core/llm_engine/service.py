from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel
import os
import dashscope
from dashscope import Generation


class QwenChatModel(BaseChatModel):
    """
    Custom wrapper for Qwen model using DashScope SDK
    """
    model_name: str = "qwen-max"
    temperature: float = 0.7
    max_tokens: int = 1024

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        """
        Generate a response from Qwen model
        """
        # Convert LangChain messages to the format expected by DashScope
        text_content = ""
        for msg in messages:
            if hasattr(msg, 'content'):
                text_content += f"{msg.content}\n"

        try:
            # Set the API key from environment
            dashscope.api_key = os.getenv("QWEN_API_KEY")

            # Call the DashScope generation API
            response = Generation.call(
                model=self.model_name,
                prompt=text_content,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                result_format='message'  # Use message format for chat
            )

            if response.status_code == 200:
                # Extract the content from the response
                content = response.output.choices[0]['message']['content']

                # Create a ChatGeneration object
                generation = ChatGeneration(
                    message=HumanMessage(content=content),
                    generation_info={"model": self.model_name}
                )

                return ChatResult(generations=[generation])
            else:
                # Return an error message if the API call failed
                error_msg = f"Qwen API Error: {response.code} - {response.message}"
                generation = ChatGeneration(
                    message=HumanMessage(content=error_msg),
                    generation_info={"error": True}
                )
                return ChatResult(generations=[generation])

        except Exception as e:
            # Handle any exceptions
            error_msg = f"Qwen API Exception: {str(e)}"
            generation = ChatGeneration(
                message=HumanMessage(content=error_msg),
                generation_info={"error": True}
            )
            return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "qwen-chat"


class LLMConfig(BaseModel):
    """Configuration for LLM service"""
    primary_model: str = "qwen-max"
    fallback_model: str = "qwen-plus"
    temperature: float = 0.7
    max_tokens: int = 1024


class LLMEngineService:
    """
    Service for managing LLM interactions using LangChain.
    Supports multiple providers (Anthropic, OpenAI, Qwen) with fallback capabilities.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.primary_client = self._initialize_primary_client()
        self.fallback_client = self._initialize_fallback_client()

    def _initialize_primary_client(self):
        """Initialize the primary LLM client based on configuration."""
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("QWEN_API_KEY")

        # If no API key is available, return a mock/fallback implementation
        if not api_key:
            # Return a dummy client that can be used for testing
            class MockClient:
                def invoke(self, messages):
                    # Simple mock response for testing
                    class MockResponse:
                        content = "This is a mock response for testing purposes. Please set your API key in the environment variables."
                    return MockResponse()
            return MockClient()

        if "qwen" in self.config.primary_model.lower():
            # Use the DashScope API key for Qwen models
            dashscope.api_key = os.getenv("QWEN_API_KEY")
            return QwenChatModel(
                model_name=self.config.primary_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
        elif "claude" in self.config.primary_model.lower():
            return ChatAnthropic(
                model=self.config.primary_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        else:
            return ChatOpenAI(
                model=self.config.primary_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=os.getenv("OPENAI_API_KEY")
            )

    def _initialize_fallback_client(self):
        """Initialize the fallback LLM client."""
        # Get API keys for different providers
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        qwen_api_key = os.getenv("QWEN_API_KEY")

        # Check which provider we're using based on the model name
        fallback_model_lower = self.config.fallback_model.lower()

        # If no API key is available, return a mock/fallback implementation
        if not any([anthropic_api_key, openai_api_key, qwen_api_key]):
            # Return a dummy client that can be used for testing
            class MockClient:
                def invoke(self, messages):
                    # Simple mock response for testing
                    class MockResponse:
                        content = "This is a fallback mock response for testing purposes. Please set your API key in the environment variables."
                    return MockResponse()
            return MockClient()

        if "qwen" in fallback_model_lower:
            if not qwen_api_key:
                # Fallback if no key is provided
                class MockClient:
                    def invoke(self, messages):
                        class MockResponse:
                            content = "Fallback mock response: QWEN_API_KEY not set"
                        return MockResponse()
                return MockClient()

            # Use the DashScope API key for Qwen models
            dashscope.api_key = os.getenv("QWEN_API_KEY")
            return QwenChatModel(
                model_name=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
        elif "claude" in fallback_model_lower:
            if not anthropic_api_key:
                # Fallback if no key is provided
                class MockClient:
                    def invoke(self, messages):
                        class MockResponse:
                            content = "Fallback mock response: ANTHROPIC_API_KEY not set"
                        return MockResponse()
                return MockClient()

            return ChatAnthropic(
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=anthropic_api_key
            )
        else:
            if not openai_api_key:
                # Fallback if no key is provided
                class MockClient:
                    def invoke(self, messages):
                        class MockResponse:
                            content = "Fallback mock response: OPENAI_API_KEY not set"
                        return MockResponse()
                return MockClient()

            return ChatOpenAI(
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=openai_api_key
            )

    def generate_response(self,
                         user_input: str,
                         context: Optional[str] = None,
                         system_prompt: Optional[str] = None) -> str:
        """
        Generate a response from the LLM based on user input and context.

        Args:
            user_input: The input from the user
            context: Additional context for the conversation
            system_prompt: System prompt to guide the model's behavior

        Returns:
            Generated response from the LLM
        """
        try:
            # Prepare messages for the LLM
            messages = []

            # Add system prompt if provided
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))

            # Add context if provided
            if context:
                messages.append(SystemMessage(content=f"Context: {context}"))

            # Add user input
            messages.append(HumanMessage(content=user_input))

            # Call the primary model
            response = self.primary_client.invoke(messages)
            return response.content

        except Exception as e:
            print(f"Primary model failed: {str(e)}")
            # Fallback to secondary model
            try:
                # Prepare messages for the fallback model
                messages = []

                # Add system prompt if provided
                if system_prompt:
                    messages.append(SystemMessage(content=system_prompt))

                # Add context if provided
                if context:
                    messages.append(SystemMessage(content=f"Context: {context}"))

                # Add user input
                messages.append(HumanMessage(content=user_input))

                # Call the fallback model
                response = self.fallback_client.invoke(messages)
                return response.content

            except Exception as fallback_e:
                print(f"Fallback model also failed: {str(fallback_e)}")
                return "Sorry, I'm currently unable to process your request. Please try again later."

    def validate_config(self) -> bool:
        """
        Validate that the required API keys are available.

        Returns:
            True if configuration is valid, False otherwise
        """
        primary_has_key = (
            "claude" in self.config.primary_model.lower() and os.getenv("ANTHROPIC_API_KEY")
        ) or (
            "gpt" in self.config.primary_model.lower() and os.getenv("OPENAI_API_KEY")
        ) or (
            "qwen" in self.config.primary_model.lower() and os.getenv("QWEN_API_KEY")
        )

        fallback_has_key = (
            "claude" in self.config.fallback_model.lower() and os.getenv("ANTHROPIC_API_KEY")
        ) or (
            "gpt" in self.config.fallback_model.lower() and os.getenv("OPENAI_API_KEY")
        ) or (
            "qwen" in self.config.fallback_model.lower() and os.getenv("QWEN_API_KEY")
        )

        return primary_has_key and fallback_has_key

    def test_connection(self) -> bool:
        """
        Test the connection to the LLM provider(s).

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            test_response = self.generate_response("Hello, are you there?", "Testing connection")
            return bool(test_response and len(test_response) > 0 and "mock" not in test_response.lower())
        except Exception:
            return False