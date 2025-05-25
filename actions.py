import webbrowser
import requests
import os
from dotenv import load_dotenv
import re
from datetime import datetime
import logging
from urllib.parse import quote
from textblob import TextBlob
from translate import Translator
import random
from typing import Any, List, Text, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet
import spacy

logger = logging.getLogger(__name__)
load_dotenv()

# Загрузка модели spaCy
try:
    nlp = spacy.load("ru_core_news_lg")
except OSError:
    nlp = spacy.load("ru_core_news_md")
except OSError:
    print("Error: spaCy model not found.  Please download one using: python -m spacy download ru_core_news_lg")
    nlp = None

# переводчик
def translate_to_english(text):
    translator = Translator(to_lang="en", from_lang="ru")
    try:
        return translator.translate(text).lower()
    except:
        return text

# слова, которые я не хочу видеть
def forbidden_func():
    try:
        with open("forbidden_file.txt", "r", encoding="utf8") as fin:
            mass = []
            f = fin.readlines()
            for line in f:
                if "\n" in line: mass.append(line.replace("\n", ""))
                else: mass.append(line)
            return mass

    except FileNotFoundError:
        print("Файл не найден")

# функция для анализа тональности
def analyze_sentiment(text):
    try:
        for char in text:
            if (65 <= ord(char) <= 90) or (97 <= ord(char) <= 122):
                return 0.0, "error"

        text = translate_to_english(text)
        analysis = TextBlob(text)
        polarity = analysis.sentiment.polarity

        # Определяем тональность
        if polarity > 0.1:
            sentiment = "позитивный"
        elif polarity < -0.1:
            sentiment = "негативный"
        else:
            sentiment = "нейтральный"

        return polarity, sentiment

    except Exception as e:
        print(f"Ошибка анализа тональности: {str(e)}")
        return 0.0, "нейтральный"


# Возвращает ответ в зависимости от тональности
def get_sentiment_response(polarity, sentiment):
    responses = {
        "error": [
            "Пишите, пожалуйста, на русском.",
        ],
        "позитивный": [
            "Я вижу у тебя хорошее настроение! Оценка тональности: {:.2f}",
            "Рад видеть вашу улыбку! Тональность: {:.2f}",
            "Какой настрой! Оценка тональности: {:.2f}"
        ],
        "негативный": [
            "Вижу день не задался( Оценка тональности: {:.2f}",
            "Кажется, тебе грустно. Тональность: {:.2f}",
            "Всё будет хорошо, не переживай. Оценка настроения: {:.2f}"
        ],
        "нейтральный": [
            "Ладно. Оценка тональности: {:.2f}",
            "Нейтральный настрой. Тональность: {:.2f}"
        ]
    }
    return random.choice(responses[sentiment]).format(polarity)


class ActionGetWeather(Action):
    def name(self) -> Text:
        return "action_get_weather"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        api_key = os.getenv("OPEN_WEATHER_KEY")
        city = next(tracker.get_latest_entity_values("city"), None)

        if not city:
            message = "Укажите город, например: 'Погода в городе Москва'"
            dispatcher.utter_message(text=message)
            return [SlotSet("last_bot_message", message)]

        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city},RU&appid={api_key}&units=metric&lang=ru"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                weather_info = (
                    f"Погода в городе {data['name']}:\n"
                    f"- Температура: {data['main']['temp']}°C\n"
                    f"- Описание: {data['weather'][0]['description'].capitalize()}\n"
                )
                dispatcher.utter_message(text=weather_info)
                message = weather_info
            else:
                message = f"Ошибка: город '{city}' не найден. Проверьте правильность ввода."
                dispatcher.utter_message(text=message)

        except Exception as e:
            logger.error(f"Weather API error: {str(e)}")
            message = "Не удалось получить информацию о погоде."
            dispatcher.utter_message(text=message)

        return [SlotSet("last_bot_message", message)]


class ActionCalculate(Action):
    def name(self) -> Text:
        return "action_calculate"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        message = tracker.latest_message.get("text")
        try:

            expr = re.search(r"(\d+)\s*([+-\/*])\s*(\d+)", message)
            if expr:
                a, op, b = expr.groups()
                a, b = int(a), int(b)

                if op == '+':
                    result = a + b
                elif op == '-':
                    result = a - b
                elif op == '*':
                    result = a * b
                elif op == '/':
                    result = a / b if b != 0 else "∞"

                message = f"Ответ: {result}"
                dispatcher.utter_message(text=message)
            else:
                message = "Некорректный ввод чисел. Как должно быть: 'Посчитай 2+2'"
                dispatcher.utter_message(text=message)

        except Exception as e:
            logger.error(f"Calculation error: {str(e)}")
            message = "Не могу вычислить данное выражение("
            dispatcher.utter_message(text=message)

        return [SlotSet("last_bot_message", message)]

# время
class ActionGetTime(Action):
    def name(self) -> Text:
        return "action_get_time"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        current_time = datetime.now().strftime("%H:%M:%S")
        current_date = datetime.now().strftime("%Y-%m-%d")

        message = f"Текущая дата: {current_date}, время: {current_time}"
        dispatcher.utter_message(text=message)
        return [SlotSet("data", current_date), SlotSet("time", current_time), SlotSet("last_bot_message", message)]


# настроение
class ActionAnalyzeSentiment(Action):
    def name(self) -> str:
        return "action_analyze_sentiment"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict):
        message = tracker.latest_message.get("text")

        # Выполняем анализ тональности
        polarity, sentiment = analyze_sentiment(message)

        # Получаем ответ в зависимости от тональности
        sentiment_response = get_sentiment_response(polarity, sentiment)

        # Отправляем сообщение с анализом тональности
        message = sentiment_response
        dispatcher.utter_message(text=message)

        return [SlotSet("last_bot_message", message)]

# инетрнет
class ActionWebSearch(Action):
    def name(self) -> Text:
        return "action_web_search"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Получаем последнее сообщение пользователя
        message = tracker.latest_message.get("text")

        result = self._perform_search(message)

        dispatcher.utter_message(text=result)
        return [SlotSet("last_bot_message", result)]

    def _perform_search(self, command: Text) -> Text:
        """Выполняет поиск в интернете через webbrowser"""
        try:
            # Проверяем, начинается ли команда с "поиск " и содержит ли она кавычки
            if command.lower().startswith('поиск "') and command.count('"') >= 2:
                # Извлекаем текст между кавычками
                query = command.split('"')[1]

                forbidden = forbidden_func()
                string_forbidden = ""

                # Проверка на запрещенные слова в запросе
                if len(query.split()) > 1:
                    for word in query.split():
                        if word in forbidden:
                            string_forbidden += word + " "

                elif query in forbidden:
                    raise ValueError(f"Недопустимое слово")

                # Если есть запрещенные слова, выводим ошибку
                if string_forbidden != "":
                    raise ValueError(
                        f"Недопустимое слово")

                # Открываем результаты поиска в браузере
                webbrowser.open(f"https://www.google.com/search?q={quote(query)}")
                message = f"Ищу: {query}"
                return message

            message = "Используйте: поиск \"запрос\""
            return message

        except Exception as e:
            message = f"Не могу найти: {str(e)}"
            return message

# рассказывает анекдот
class ActionRandomSong(Action):
    def name(self) -> str:
        return "action_random_song"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict,
    ) -> List[Dict[Text, Any]]:
        songs = [
            "Знаешь почему у людоеда нет друзей? Потому что он сыт по горло.",
            "А знаешь как слепые преодолевают препятствия? Не смотря ни на что.",
            "Как называется место на кладбище, где сидит охранник? Живой уголок.",
            "Как называется обувь отца? Батинки.",
            "Шел как-то Бог по раю, видит, два сада горит. На грушевый вообще всё равно, а яблочный спас.",
            "Почему компьютер замерз? У него было открыто слишком много окон.",
        ]

        if not songs:
            message = "Я ещё не придумал анекдот."
            dispatcher.utter_message(text=message)
            return [SlotSet("last_bot_message", message)]

        song = random.choice(songs)
        message = f"Ну слушай: {song}"
        dispatcher.utter_message(text=message)

        return [SlotSet("last_bot_message", message)]

class ActionRememberName(Action):
    def name(self) -> Text:
        return "action_remember_name"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = domain.get("config", {}).get("language", "ru")
        text = tracker.latest_message.get("text")

        if nlp is None:
            message = "К сожалению, я не могу сейчас запомнить ваше имя.  Пожалуйста, попробуйте позже."
            dispatcher.utter_message(text=message)
            return [SlotSet("last_bot_message", message)]

        doc = nlp(text)
        name = next((ent.text for ent in doc.ents if ent.label_ == "PER"), None)

        if not name:
            dispatcher.utter_message(response_key="utter_ask_name") # ИСПРАВЛЕНО
            return []

        message = f"Приятно познакомиться, {name}!" if lang == "ru" else f"Nice to meet you, {name}!"
        dispatcher.utter_message(text=message)
        return [SlotSet("name", name), SlotSet("last_bot_message", message)]


class ActionGetName(Action):
    def name(self) -> Text:
        return "action_get_name"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = domain.get("config", {}).get("language", "ru")
        name = tracker.get_slot("name")

        if name:
            message = f"Тебя зовут {name}, верно?" if lang == "ru" else f"Your name is {name}, right?"
        else:
            message = "Я пока не знаю, как тебя зовут." if lang == "ru" else "I don't know your name yet."

        dispatcher.utter_message(text=message)
        return [SlotSet("last_bot_message", message)]