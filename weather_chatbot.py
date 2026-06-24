"""
Weather Chatbot using Mistral AI API
Provides intelligent weather-related conversations and recommendations
"""
import os
import logging
from datetime import datetime
from mistralai.client import Mistral

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeatherChatbot:
    """Weather chatbot powered by Mistral AI"""
    
    def __init__(self, api_key=None):
        """
        Initialize the Weather Chatbot
        
        Args:
            api_key (str): Mistral API key. If None, uses MISTRAL_API_KEY env var
        """
        self.api_key = api_key or os.getenv('MISTRAL_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "Mistral API key not found. Set MISTRAL_API_KEY environment variable "
                "or pass it to WeatherChatbot()"
            )
        
        self.client = Mistral(api_key=self.api_key)
        self.model = "mistral-small-latest"  # Using Mistral Small for faster responses
        
        # System prompt for the weather chatbot (French + HTML format)
        self.system_prompt = """Vous êtes l'assistant IA météo et qualité de l'air d'AirPredict.
Votre rôle est de répondre aux questions des utilisateurs en français de manière claire, chaleureuse et structurée.

Consignes obligatoires de formatage et de style :
1. Répondez TOUJOURS en français.
2. Structurez votre réponse avec des sections courtes et distinctes.
3. Utilisez des émojis appropriés au début des points clés pour rendre la lecture agréable.
4. IMPORTANT : Formatez votre réponse DIRECTEMENT en HTML brut. Utilisez uniquement les balises suivantes :
   - <p>...</p> pour les paragraphes ordinaires.
   - <strong>...</strong> pour mettre en valeur les mots importants.
   - <br> pour les retours à la ligne simples.
   - <h3>...</h3> pour les titres de section/rubriques.
   - <ul>...</ul> et <li>...</li> pour les listes à puces.
5. Ne mettez AUCUN bloc de code Markdown ou enveloppe de code comme ```html ou ```. Retournez directement le HTML brut.
6. Restez focalisé sur la météo, la qualité de l'air, la santé et les conseils associés. Ne proposez rien qui sorte de ce cadre."""

        # System prompt for the enterprise chatbot
        self.enterprise_system_prompt = """Vous êtes l'assistant IA industriel et environnemental d'AirPredict Entreprise.
Votre rôle est d'analyser les émissions de CO2 des usines industrielles, d'évaluer l'efficacité des systèmes de lavage de CO2 (CO2 Wash) et de proposer des solutions d'optimisation énergétique pour réduire l'empreinte carbone.

Consignes obligatoires de formatage et de style :
1. Répondez TOUJOURS en français dans un ton professionnel, analytique et orienté solution B2B.
2. Formatez DIRECTEMENT en HTML brut (sans bloc markdown ```html). Utilisez <p>, <strong>, <br>, <h3>, <ul>, <li>.
3. Résumez les émissions de manière claire, et proposez toujours 2 ou 3 pistes d'optimisation technique.
4. Restez concentré sur l'industrie, le CO2, l'efficacité énergétique et la qualité de l'air industriel."""
        
        self.conversation_history = []
    
    def reset_conversation(self):
        """Reset the conversation history"""
        self.conversation_history = []

    def _resolve_message_content(self, message):
        """Normalise le contenu d'une réponse Mistral en chaîne de caractères."""
        if message is None:
            return ""
        content = getattr(message, 'content', '')
        if isinstance(content, list):
            resolved = []
            for chunk in content:
                chunk_content = getattr(chunk, 'content', None)
                if chunk_content is None:
                    chunk_content = str(chunk)
                resolved.append(str(chunk_content))
            return ''.join(resolved)
        return str(content)

    def chat(self, user_message, weather_context=None, mode='standard'):
        """
        Send a message to the chatbot and get a response
        
        Args:
            user_message (str): User's message
            weather_context (dict): Optional weather data to include in context
        
        Returns:
            dict: Response with 'message' and metadata
        """
        try:
            # Build context from weather data if provided
            context_str = ""
            if weather_context:
                context_str = self._build_weather_context(weather_context)
            
            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })
            
            # Select appropriate system prompt based on mode
            active_prompt = self.enterprise_system_prompt if mode == 'enterprise' else self.system_prompt
            
            # Prepare messages for API (dict format for mistralai 2.x)
            messages = [
                {"role": "system", "content": active_prompt}
            ]
            
            # Add weather context if available
            if context_str:
                messages.append({
                    "role": "system",
                    "content": f"Current weather context:\n{context_str}"
                })
            
            # Add conversation history (keep last 10 messages)
            for msg in self.conversation_history[-10:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Call Mistral API
            response = self.client.chat.complete(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=512
            )
            
            # Extract response text
            assistant_message = self._resolve_message_content(response.choices[0].message).strip()
            
            # Add to history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return {
                "message": assistant_message,
                "status": "success",
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Chatbot error: {str(e)}")
            return {
                "message": f"Error: {str(e)}",
                "status": "error",
                "timestamp": datetime.now().isoformat()
            }
    
    def get_weather_advice(self, temperature, humidity, weather_type, air_quality=None):
        """
        Get specific weather advice based on current conditions
        
        Args:
            temperature (float): Temperature in Celsius
            humidity (float): Humidity percentage
            weather_type (str): Type of weather (sunny, rainy, cloudy, etc.)
            air_quality (dict): Optional air quality data
        
        Returns:
            dict: Weather advice from the chatbot
        """
        context = {
            "temperature": temperature,
            "humidity": humidity,
            "weather_type": weather_type,
            "air_quality": air_quality
        }
        
        prompt = f"""Based on the current weather conditions:
- Temperature: {temperature}°C
- Humidity: {humidity}%
- Weather type: {weather_type}
{"- Air quality: " + str(air_quality) if air_quality else ""}

Please provide:
1. Health recommendations for these conditions
2. Suggested outdoor activities (if appropriate)
3. Any safety warnings or precautions"""
        
        return self.chat(prompt, weather_context=context)
    
    def generate_industrial_recommendations(self, entity_name: str, entity_type: str, pollution_summary: dict) -> str:
        """
        Génère un plan d'action environnemental personnalisé via Mistral AI
        pour une entité industrielle (Usine, Ville ou Pays).

        Le prompt positionne Mistral comme expert en ingénierie environnementale
        et décarbonation industrielle. La réponse est retournée en HTML propre
        (balises h3/p/ul/li uniquement) — aucun bloc Markdown, aucun JS.

        Args:
            entity_name    (str) : Nom de l'entité (ex. "Usine Nord Casablanca")
            entity_type    (str) : Type — "Usine", "Ville" ou "Pays"
            pollution_summary (dict): Facteurs de pollution avec leur taux/pourcentage.
                Exemple: {'CO': 42.3, 'CO2': 78.1, 'PM2.5': 55.0, 'PM10': 34.7}

        Returns:
            str: HTML brut prêt à être injecté via |safe dans Jinja2.
                 Retourne un message d'erreur en HTML en cas d'échec API.
        """
        # ---- Prompt système : expert en décarbonation industrielle ----
        industrial_system_prompt = (
            "Vous êtes un Expert senior en ingénierie environnementale et décarbonation industrielle, "
            "spécialisé dans la réduction des émissions atmosphériques pour des entités industrielles "
            "(usines, villes, pays). Votre rôle est d'analyser des données de capteurs de pollution "
            "et de proposer des solutions concrètes, réalistes et hiérarchisées pour réduire l'impact "
            "environnemental.\n\n"
            "CONSIGNES DE FORMATAGE OBLIGATOIRES :\n"
            "1. Répondez EXCLUSIVEMENT en français, ton professionnel et analytique.\n"
            "2. Retournez DIRECTEMENT du HTML brut — SANS bloc ```html ni ``` ni tout autre marqueur Markdown.\n"
            "3. Utilisez UNIQUEMENT ces balises HTML : <h3>, <p>, <ul>, <li>, <strong>.\n"
            "4. Structurez la réponse en 3 sections : Analyse du profil de pollution, "
            "Plan d'action prioritaire (au moins 4 mesures concrètes), Indicateurs de suivi recommandés.\n"
            "5. Chaque mesure doit mentionner le polluant ciblé, la technologie ou méthode proposée, "
            "et l'impact attendu en pourcentage de réduction.\n"
            "6. Rédigez chaque section en détail, avec au moins 3 à 4 phrases par paragraphe. "
            "N'écourtez pas votre réponse — complétez toujours les trois sections en entier."
        )

        # ---- Construction du résumé lisible des facteurs de pollution ----
        if pollution_summary:
            facteurs_str = "\n".join(
                f"  - {k} : {v:.1f} % du seuil critique"
                for k, v in pollution_summary.items()
            )
        else:
            facteurs_str = "  - Données non disponibles"

        # ---- Message utilisateur structuré ----
        user_prompt = (
            f"Entité analysée : {entity_name} (Type : {entity_type})\n\n"
            f"Données capteurs internes — taux de pollution par rapport aux seuils critiques :\n"
            f"{facteurs_str}\n\n"
            f"En tant qu'expert en décarbonation industrielle, génère un plan d'action environnemental "
            f"complet et opérationnel pour cette {entity_type.lower()}. "
            f"Priorise les polluants les plus élevés et propose des technologies adaptées à l'échelle "
            f"de l'entité ({entity_type})."
        )

        try:
            logger.info(
                f"Génération recommandations industrielles pour «{entity_name}» ({entity_type})"
            )
            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": industrial_system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.6,   # Légèrement déterministe pour des recommandations cohérentes
                max_tokens=2000,
            )
            html_result = self._resolve_message_content(response.choices[0].message).strip()
            finish_reason = getattr(response.choices[0], 'finish_reason', None)

            # Si la réponse est tronquée par la limite de tokens, on demande une continuation
            if finish_reason == 'length':
                logger.warning('Réponse Mistral tronquée, demande de continuation.')
                continuation = self.client.chat.complete(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": industrial_system_prompt},
                        {"role": "user", "content": (
                            "Poursuis la réponse précédente en HTML là où elle s'est arrêtée. "
                            "Ne répète pas l'introduction, termine directement le contenu restant."
                            f"\n\nRéponse précédente :\n{html_result}"
                        )},
                    ],
                    temperature=0.6,
                    max_tokens=1000,
                )
                additional = self._resolve_message_content(continuation.choices[0].message).strip()
                html_result = f"{html_result}\n{additional}"

            # Sécurité : supprimer les éventuels blocs Markdown si le modèle les ajoute quand même
            if html_result.startswith("```"):
                # Retirer la première ligne (```html ou ```) et la dernière (```) 
                lines = html_result.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                html_result = "\n".join(lines)

            logger.info("Recommandations industrielles générées avec succès.")
            return html_result

        except Exception as exc:
            logger.error(f"Erreur Mistral recommendations industrielles : {exc}")
            return (
                "<h3>⚠️ Service IA temporairement indisponible</h3>"
                "<p>Le plan d'action environnemental n'a pas pu être généré. "
                "Veuillez vérifier votre clé API Mistral et réessayer.</p>"
                f"<p><strong>Détail technique :</strong> {exc}</p>"
            )

    def _build_weather_context(self, weather_data):
        """Build a readable weather context string"""
        context = []
        
        if "temperature" in weather_data:
            context.append(f"Temperature: {weather_data['temperature']}°C")
        
        if "humidity" in weather_data:
            context.append(f"Humidity: {weather_data['humidity']}%")
        
        if "weather_type" in weather_data:
            context.append(f"Weather type: {weather_data['weather_type']}")
        
        if "wind_speed" in weather_data:
            context.append(f"Wind speed: {weather_data['wind_speed']} km/h")
        
        if "air_quality" in weather_data:
            context.append(f"Air quality: {weather_data['air_quality']}")
        
        return "\n".join(context)


# Singleton instance
_chatbot_instance = None


def get_chatbot(api_key=None):
    """Get or create the chatbot instance"""
    global _chatbot_instance
    
    if _chatbot_instance is None:
        _chatbot_instance = WeatherChatbot(api_key)
    
    return _chatbot_instance
