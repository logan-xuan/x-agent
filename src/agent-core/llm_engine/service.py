from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
import os


class LLMConfig(BaseModel):
    """Configuration for LLM service"""
    primary_model: str = "claude-3-5-sonnet-20241022"
    fallback_model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1024


class LLMEngineService:
    """
    Service for managing LLM interactions using LangChain.
    Supports multiple providers (Anthropic, OpenAI) with fallback capabilities.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.primary_client = self._initialize_primary_client()
        self.fallback_client = self._initialize_fallback_client()

    def _initialize_primary_client(self):
        """Initialize the primary LLM client based on configuration."""
        if "claude" in self.config.primary_model.lower():
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
        if "claude" in self.config.fallback_model.lower():
            return ChatAnthropic(
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        else:
            return ChatOpenAI(
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=os.getenv("OPENAI_API_KEY")
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
        )

        fallback_has_key = (
            "claude" in self.config.fallback_model.lower() and os.getenv("ANTHROPIC_API_KEY")
        ) or (
            "gpt" in self.config.fallback_model.lower() and os.getenv("OPENAI_API_KEY")
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
            return bool(test_response and len(test_response) > 0)
        except Exception:
            return False