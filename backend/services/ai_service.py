import os
import logging
from typing import List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel
import json

logger = logging.getLogger(__name__)

class AIAnalysis(BaseModel):
    intent: str
    sentiment: str
    priority: str
    is_spam: bool
    confidence: float
    suggested_response: Optional[str] = None

class AIService:
    def __init__(self):
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key and api_key != 'your_openai_api_key_here':
            self.client = AsyncOpenAI(api_key=api_key)
            self.model = os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo')
            self.api_available = True
        else:
            self.client = None
            self.model = None
            self.api_available = False
            logger.warning("OpenAI API key not configured. Using fallback analysis only.")
        
    async def analyze_message(self, content: str, conversation_history: List[str] = None) -> AIAnalysis:
        """Analyze message for sentiment, intent, priority, and spam detection"""
        if not self.api_available:
            logger.info("Using fallback analysis (OpenAI not available)")
            return self._fallback_analysis(content)
            
        try:
            history_context = ""
            if conversation_history:
                history_context = f"\nRecent conversation context:\n" + "\n".join(conversation_history[-3:])
            
            prompt = f"""
            Analyze this customer message for a business conversation:
            
            Message: "{content}"{history_context}
            
            Provide analysis in JSON format with:
            - intent: one of [inquiry, complaint, support_request, sales, feedback, general]
            - sentiment: one of [positive, negative, neutral]
            - priority: one of [high, medium, low] 
            - is_spam: boolean
            - confidence: float between 0-1
            - suggested_response: brief professional response (max 100 words)
            
            Return only valid JSON.
            """
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a customer service AI assistant. Analyze messages and return JSON responses."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Try to parse JSON response
            try:
                analysis_data = json.loads(result_text)
                
                # Validate and normalize values
                intent = analysis_data.get('intent', 'general')
                if intent not in ['inquiry', 'complaint', 'support_request', 'sales', 'feedback', 'general']:
                    intent = 'general'
                
                sentiment = analysis_data.get('sentiment', 'neutral')
                if sentiment not in ['positive', 'negative', 'neutral']:
                    sentiment = 'neutral'
                
                priority = analysis_data.get('priority', 'medium')
                if priority not in ['high', 'medium', 'low']:
                    priority = 'medium'
                
                is_spam = bool(analysis_data.get('is_spam', False))
                confidence = float(analysis_data.get('confidence', 0.5))
                confidence = max(0.0, min(1.0, confidence))  # Clamp between 0-1
                
                suggested_response = analysis_data.get('suggested_response')
                if suggested_response and len(suggested_response) > 200:
                    suggested_response = suggested_response[:200] + "..."
                
                return AIAnalysis(
                    intent=intent,
                    sentiment=sentiment,
                    priority=priority,
                    is_spam=is_spam,
                    confidence=confidence,
                    suggested_response=suggested_response
                )
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse AI response as JSON: {result_text}")
                # Fallback to basic analysis
                return self._fallback_analysis(content)
                
        except Exception as e:
            logger.error(f"AI analysis failed: {str(e)}")
            return self._fallback_analysis(content)
    
    def _fallback_analysis(self, content: str) -> AIAnalysis:
        """Fallback analysis when AI service fails"""
        content_lower = content.lower()
        
        # Basic keyword-based analysis
        if any(word in content_lower for word in ['urgent', 'emergency', 'asap', 'immediately']):
            priority = 'high'
        elif any(word in content_lower for word in ['help', 'issue', 'problem', 'broken']):
            priority = 'medium'
        else:
            priority = 'low'
        
        if any(word in content_lower for word in ['angry', 'frustrated', 'terrible', 'worst']):
            sentiment = 'negative'
        elif any(word in content_lower for word in ['happy', 'great', 'excellent', 'thank']):
            sentiment = 'positive'
        else:
            sentiment = 'neutral'
        
        if any(word in content_lower for word in ['buy', 'price', 'cost', 'quote']):
            intent = 'sales'
        elif any(word in content_lower for word in ['help', 'support', 'fix', 'issue']):
            intent = 'support_request'
        elif any(word in content_lower for word in ['complaint', 'unhappy', 'dissatisfied']):
            intent = 'complaint'
        else:
            intent = 'general'
        
        # Basic spam detection
        spam_keywords = ['click here', 'free money', 'winner', 'congratulations', 'limited offer']
        is_spam = any(keyword in content_lower for keyword in spam_keywords)
        
        return AIAnalysis(
            intent=intent,
            sentiment=sentiment,
            priority=priority,
            is_spam=is_spam,
            confidence=0.6,
            suggested_response="Thank you for your message. Our team will review and respond shortly."
        )

# Global AI service instance
ai_service = AIService()
