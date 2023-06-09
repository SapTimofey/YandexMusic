import yandex_music
from yandex_music import Client, Track

import discord
from discord import Embed, SelectOption, ButtonStyle, app_commands
from discord.ext import commands
from discord.ui import Button, View, Select

import asyncio
import os
import datetime
import requests
import textwrap
import re
from pytube import YouTube
# from pydub import AudioSegment
from googleapiclient.discovery import build
from random import random


# Инициализируем Discord клиент
intents = discord.Intents.all()
intents.members = True
intents.messages = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
bot = commands.Bot(command_prefix='!', intents=intents)


'''
Глобальные переменные
'''
tokens = {}
birthdays = {}
google_token = None
YM_token = None
settings_onyourwave = {}
user = os.environ.get('USERNAME')
output_path = f'C:\\Users\\{user}\\Music'  # Путь к папке, где будет сохранен аудиофайл
data_server = {
    'playlist': [],
    'repeat_flag': False,
    'queue_repeat': '',
    'index_play_now': 0,
    'task': None,
    'task_reserv': None,
    'task_check_voice_clients': None,
    'task_check_inactivity': None,
    'lyrics': None,
    'track_url': None,
    'cover_url': None,
    'track_id_play_now': None,
    'index_play_now': 0,
    'radio': None,
    'user_discord_play': None,
    'radio_check': False,
    'stream_by_track_check': False,
    'last_activity_time': datetime.datetime.now(),
    'message_check': '',
    'command_now': 0,
    'duration': 0
    }
data_servers = {}


# Загрузка токенов пользователей
if os.path.exists("tokens.txt") and os.path.getsize("tokens.txt") > 0:
    # загружаем данные из файла в глобальный словарь
    with open("tokens.txt", "r") as f:
        # читаем строки из файла
        lines = f.readlines()
        # перебираем строки и добавляем каждую пару ключ-значение в глобальный словарь
        for line in lines:
            # удаляем символы переноса строки и разделяем данные по пробелу
            user_discord, token = line.strip().rsplit(maxsplit=1)
            if user_discord == 'google':
                google_token = token
            elif user_discord == 'YandexMusic':
                YM_token = token
            else:
                # добавляем пару ключ-значение в глобальный словарь
                tokens[user_discord] = token
                birthdays[user_discord] = False


'''
Функции для обработки команд
'''
async def milliseconds_to_time(milliseconds):
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
async def birthday_send(interaction: discord.Interaction):
    global birthdays
    if str(interaction.user) in tokens:
        birthdays[str(interaction.user)] = True
        client_ym = Client(tokens[str(interaction.user)]).init()
        if client_ym.me.account.now.split('T')[0].split('-', maxsplit=1)[1] == \
                client_ym.me.account.birthday.split('-', maxsplit=1)[1]:
            await interaction.response.send_message(f"С Днём Рождения {client_ym.me.account.first_name} 🎉🎊",
                                                    ephemeral=True)
async def remove_last_playing_message(interaction: discord.Interaction):
    async for message in interaction.channel.history():
        if message.author == client.user and \
                (message.content.startswith('Текст') or
                 message.content.startswith('Треки в очереди') or
                 message.content.startswith('Не удалось') or
                 message.content.startswith('Произошла ошибка') or
                 len(message.embeds) > 0):
            try:
                await message.delete()
            except Exception:
                pass
async def check_voice_clients(interaction: discord.Interaction):
    global data_servers, data_servers_log
    voice_client = interaction.guild.voice_client
    while True:
        # Проверка наличия пользователей в голосовом канале
        if voice_client and not any(member != client.user for member in voice_client.channel.members):
            await disconnect(interaction)
            break
        await asyncio.sleep(0.1)
async def check_inactivity(interaction: discord.Interaction):
    global data_servers
    voice_client = interaction.guild.voice_client
    while True:
        # проверяем, прошло ли более 5 минут с момента последней активности бота
        if datetime.datetime.now() - data_servers[interaction.guild.name]['last_activity_time'] > \
                datetime.timedelta(minutes=5) and not voice_client.is_playing() and voice_client:
            await disconnect(interaction)
            break
        await asyncio.sleep(1)
async def disconnect(interaction: discord.Interaction):
    global data_servers
    voice_client = interaction.guild.voice_client
    try:
        await remove_last_playing_message(interaction)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
        data_servers[interaction.guild.name]['task'].cancel()
        await voice_client.disconnect()
        data_servers[interaction.guild.name]['task_check_inactivity'].cancel()
        data_servers[interaction.guild.name]['task_check_voice_clients'].cancel()
        data_servers[interaction.guild.name] = data_server.copy()
    except Exception:
        pass
async def check_audio_file(path):
    audio = AudioSegment.from_file(path)
    bitrate = audio.frame_rate * audio.channels * audio.sample_width * 8
    # print("bitrate = ", bitrate, "\nframe_rate = ", audio.frame_rate, "\nChannels = ", audio.channels, "\nsample_width = ", audio.sample_width)
    if (500 < bitrate < 512000):
        return True
    return False
async def add_queue(ctx, url_or_trackname_or_filepath):
    global index_queue

    playlist_ym = url_or_trackname_or_filepath.split(',')
    playlist_id = playlist_ym[0]

    client_ym = Client(tokens[user_discord]).init()

    try:
        playlist_new = client_ym.users_playlists(playlist_id)
    except Exception:
        await ctx.send(content=f"Не удалось найти плейлист с ID {playlist_id}")
        return

    if len(playlist_ym) == 1:
        for i in range(len(playlist_new.tracks)):
            playlists[ctx.guild.name].append(f"{user_discord}|{playlist_id},{i + 1}")
    else:
        if "-" in playlist_ym[1]:
            playlist_b_e = playlist_ym[1].split('-')

            if playlist_b_e[1] == '':
                index_begin = int(playlist_b_e[0])
                index_track = index_begin

                if index_track > len(playlist_new.tracks):
                    await ctx.send(
                        f"\"{index_track}\" - номер трека превышает количество треков в плейлисте \"{len(playlist_new.tracks)}\"")
                    return
                elif index_track <= 0:
                    await ctx.send(f"\"{index_track}\" - номер трека должен быть больше 0 🙃")
                    return

                for i in range(index_begin - 1, len(playlist_new.tracks)):
                    playlists[ctx.guild.name].append(f"{user_discord}|{playlist_id},{i + 1}")
            elif playlist_b_e[0] == '':
                index_end = int(playlist_b_e[1])

                if index_end > len(playlist_new.tracks):
                    await ctx.send(
                        f"\"{index_end}\" - номер трека превышает количество треков в плейлисте \"{len(playlist_new.tracks)}\"")
                    return
                elif index_end <= 0:
                    await ctx.send(f"\"{index_end}\" - номер трека должен быть больше 0 🙃")
                    return

                for i in range(index_end):
                    playlists[ctx.guild.name].append(f"{user_discord}|{playlist_id},{i + 1}")
            else:
                index_begin = int(playlist_b_e[0])
                index_end = int(playlist_b_e[1])

                if index_end > len(playlist_new.tracks):
                    await ctx.send(
                        f"\"{index_end}\" - номер трека превышает количество треков в плейлисте \"{len(playlist_new.tracks)}\"")
                    return
                elif index_end <= 0:
                    await ctx.send(f"\"{index_end}\" - номер трека должен быть больше 0 🙃")
                    return
                elif index_begin > index_end:
                    await ctx.send(
                        f"\"{index_end}\" - номер окончания плейлиста должен быть больше номера начала 🙃")
                    return

                for i in range(index_begin - 1, index_end):
                    playlists[ctx.guild.name].append(f"{user_discord}|{playlist_id},{i + 1}")
        else:
            index_track = int(playlist_ym[1])
            playlists[ctx.guild.name].append(f"{user_discord}|{playlist_id},{index_track}")
async def play_YouTube(url_or_trackname_or_filepath, user_discord, interaction: discord.Interaction):
    global data_servers

    data_servers[interaction.guild.name]['track_url'] = url_or_trackname_or_filepath
    data_servers[interaction.guild.name]['track_id_play_now'] = None
    data_servers[interaction.guild.name]['radio_check'] = False
    data_servers[interaction.guild.name]['stream_by_track_check'] = False

    # Извлеките идентификатор видео из ссылки
    video_id = re.findall(r'v=(\w+)', url_or_trackname_or_filepath)[0]

    # Создайте объект YouTube API
    youtube = build('youtube', 'v3', developerKey=google_token)

    # Получите информацию о видео
    video_info = youtube.videos().list(part='snippet', id=video_id).execute()

    # Извлеките название видео из полученных данных
    play_now = f"Название видео: {video_info['items'][0]['snippet']['title']}\nАвтор: {video_info['items'][0]['snippet']['channelTitle']}"

    # Извлеките URL превью из полученных данных
    data_servers[interaction.guild.name]['cover_url'] = video_info['items'][0]['snippet']['thumbnails']['high']['url']

    audio_file_path = f'{output_path}\\YT_{str(user_discord)}.mp3'

    yt = YouTube(url_or_trackname_or_filepath)

    # Выбираем аудио поток с максимальным битрейтом
    audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()

    # Скачиваем аудио
    audio_stream.download(output_path=output_path, filename=f'YT_{str(user_discord)}.mp3')

    return [play_now, audio_file_path]
async def play_Yandex_Music_url(interaction: discord.Interaction, url_or_trackname_or_filepath, user_discord):
    global data_servers
    data_servers[interaction.guild.name]['user_discord_play'] = user_discord
    numbers = [int(s) for s in url_or_trackname_or_filepath.split('/') if s.isdigit()]
    error_count = 0
    while error_count < 3:
        try:
            client_ym = Client(tokens[str(user_discord)]).init()

            if len(numbers) == 1:
                track_id = numbers[0]
                track = client_ym.tracks(track_id)[0]
            else:
                album_id = numbers[0]
                track_id = numbers[1]
                track = client_ym.tracks(f'{track_id}:{album_id}')[0]

            track.download(f'C:\\Users\\{user}\\Music\\YM_{user_discord}.mp3')
            data_servers[interaction.guild.name]['track_id_play_now'] = track.id
            data_servers[interaction.guild.name]['duration'] = track.duration_ms

            try:
                data_servers[interaction.guild.name]['lyrics'] = track.get_lyrics().fetch_lyrics()
            except yandex_music.exceptions.NotFoundError:
                data_servers[interaction.guild.name]['lyrics'] = None

            base_url = 'https://music.yandex.ru/track/'
            data_servers[interaction.guild.name]['track_url'] = base_url + str(track_id)

            if track.cover_uri:
                data_servers[interaction.guild.name]['cover_url'] = \
                    f"https://{track.cover_uri.replace('%%', '200x200')}"
            else:
                data_servers[interaction.guild.name]['cover_url'] = None

            artists = track.artists
            if not artists:
                artist_all = ""
            else:
                artist_names = [artist.name for artist in artists]  # получаем список имен артистов
                artist_all = ", ".join(artist_names)  # объединяем их через запятую
            play_now = ""
            if data_servers[interaction.guild.name]['radio_check']:
                play_now += "\nРадио: Моя волна"
            elif data_servers[interaction.guild.name]['stream_by_track_check']:
                play_now += "\nРадио: Моя волна по треку"
            play_now += f"\nТрек: {track.title}" + \
                        f"\nИсполнители: {artist_all}"

            audio_file_path = f'{output_path}\\YM_{user_discord}.mp3'

            return [play_now, audio_file_path]
        except Exception as e:
            if error_count < 2:
                await interaction.channel.send(f'Произошла ошибка: {e}. Подождите')
                await asyncio.sleep(1)
                error_count += 1
            else:
                await interaction.channel.send("Не удалось установить соединение с сервисом Яндекс.Музыка")
                return False
async def play_Yandex_Music_playlist(interaction: discord.Interaction, url_or_trackname_or_filepath, user_discord):
    global data_servers
    error_count = 0
    playlist_ym = url_or_trackname_or_filepath.split(',')
    playlist_id = playlist_ym[0]

    data_servers[interaction.guild.name]['user_discord_play'] = user_discord

    while error_count < 3:
        try:
            client_ym = Client(tokens[str(user_discord)]).init()
            if playlist_id == "3":
                playlist_new = client_ym.users_likes_tracks()
            else:
                try:
                    playlist_new = client_ym.users_playlists(playlist_id)
                except yandex_music.exceptions.NotFoundError:
                    p = await send_search_request(interaction, url_or_trackname_or_filepath, user_discord)
                    if not p:
                        return False

                    play_now = p[0]
                    audio_file_path = p[1]
                    return [play_now, audio_file_path]
            if not data_servers[interaction.guild.name]['playlist']:
                for i in range(len(playlist_new.tracks)):
                    track_short = playlist_new.tracks[i]
                    track = client_ym.tracks(track_short.track_id)[0]
                    if track.available:
                        data_servers[interaction.guild.name]['playlist'].append(f"{user_discord}|{playlist_id},{i + 1}")

            try:
                track_short = playlist_new.tracks[int(playlist_ym[1]) - 1]
                index_track = int(playlist_ym[1])
            except IndexError:
                track_short = playlist_new.tracks[0]
                index_track = 1

            track = client_ym.tracks(track_short.track_id)[0]

            artists = track.artists
            if not artists:
                artist_all = ""
            else:
                artist_names = [artist.name for artist in artists]  # получаем список имен артистов
                artist_all = ", ".join(artist_names)  # объединяем их через запятую
            if playlist_id == "3":
                play_now = "\nПлейлист: Мне нравится"
            else:
                play_now = f"\nПлейлист: {playlist_new.title}"
            play_now += f"\nТрек: {track.title}" + \
                        f"\nИсполнители: {artist_all}" + \
                        f"\nНомер трека: {index_track}\\{len(playlist_new.tracks)}"

            track.download(f'C:\\Users\\{user}\\Music\\YM_{user_discord}.mp3')
            data_servers[interaction.guild.name]['duration'] = track.duration_ms

            try:
                data_servers[interaction.guild.name]['lyrics'] = track.get_lyrics().fetch_lyrics()
            except yandex_music.exceptions.NotFoundError:
                data_servers[interaction.guild.name]['lyrics'] = None
            except ValueError:
                data_servers[interaction.guild.name]['lyrics'] = None

            if track.desired_visibility:
                data_servers[interaction.guild.name]['track_url'] = None
                data_servers[interaction.guild.name]['track_id_play_now'] = None
            else:
                data_servers[interaction.guild.name]['track_id_play_now'] = track.id
                base_url = 'https://music.yandex.ru/track/'
                if ":" in track_short.track_id:
                    data_servers[interaction.guild.name]['track_url'] = \
                        base_url + str(track_short.track_id).split(":")[0]
                else:
                    data_servers[interaction.guild.name]['track_url'] = base_url + str(track_short.track_id)

            if track.cover_uri:
                data_servers[interaction.guild.name]['cover_url'] = \
                    f"https://{track.cover_uri.replace('%%', '200x200')}"
            else:
                data_servers[interaction.guild.name]['cover_url'] = None

            audio_file_path = f'{output_path}\\YM_{user_discord}.mp3'

            return [play_now, audio_file_path]
        except Exception as e:
            if error_count < 2:
                await interaction.channel.send(f'Произошла ошибка: {e}. Подождите')
                await asyncio.sleep(1)
                error_count += 1
            else:
                await interaction.channel.send("Не удалось установить соединение с сервисом Яндекс.Музыка")
                return False
async def send_search_request(interaction: discord.Interaction, query, user_discord):
    global data_servers
    data_servers[interaction.guild.name]['user_discord_play'] = user_discord
    type_to_name = {
        'track': 'трек',
        'artist': 'исполнитель',
        'album': 'альбом',
        'playlist': 'плейлист',
        'video': 'видео',
        'user': 'пользователь',
        'podcast': 'подкаст',
        'podcast_episode': 'эпизод подкаста',
    }
    error_count = 0

    while error_count < 3:
        try:
            client_ym = Client(tokens[str(user_discord)]).init()

            search_result = client_ym.search(query)

            type_ = search_result.best.type
            best = search_result.best.result
            if type_ in ['track', 'podcast_episode']:
                track = client_ym.tracks(best.track_id)[0]
                data_servers[interaction.guild.name]['track_id_play_now'] = track.id
                data_servers[interaction.guild.name]['duration'] = track.duration_ms
                artists = track.artists
                if not artists:
                    artist_all = ""
                else:
                    artist_names = [artist.name for artist in artists]  # получаем список имен артистов
                    artist_all = ", ".join(artist_names)  # объединяем их через запятую
                play_now = f"\nТрек: {track.title}\nИсполнители: {artist_all}"

                track.download(f'{output_path}\\YM_{user_discord}.mp3')

                try:
                    data_servers[interaction.guild.name]['lyrics'] = track.get_lyrics().fetch_lyrics()
                except yandex_music.exceptions.NotFoundError:
                    data_servers[interaction.guild.name]['lyrics'] = None

                if track.desired_visibility:
                    data_servers[interaction.guild.name]['track_url'] = None
                else:
                    base_url = 'https://music.yandex.ru/track/'
                    if ":" in track.track_id:
                        data_servers[interaction.guild.name]['track_url'] = base_url + str(track.track_id).split(":")[0]
                    else:
                        data_servers[interaction.guild.name]['track_url'] = base_url + str(track.track_id)

                if track.cover_uri:
                    data_servers[interaction.guild.name]['cover_url'] = f"https://{track.cover_uri.replace('%%', '200x200')}"
                else:
                    data_servers[interaction.guild.name]['cover_url'] = None

                audio_file_path = f'{output_path}\\YM_{user_discord}.mp3'

                return [play_now, audio_file_path]
            else:
                data_servers[interaction.guild.name]['track_id_play_now'] = None
                await interaction.response.send_message("Не удалось найти трек с таким названием", ephemeral=True)
                return False
        except Exception as e:
            if error_count < 2:
                await interaction.channel.send(f'Произошла ошибка: {e}. Подождите')
                await asyncio.sleep(1)
                error_count += 1
            else:
                await interaction.channel.send("Не удалось установить соединение с сервисом Яндекс.Музыка")
                return False
async def play_radio(interaction: discord.Interaction, user_discord=None, first_track: bool = False, station_id: str = None, station_from: str = None, new_task: bool=False):
    global data_servers
    error_count = 0
    while error_count < 3:
        try:
            if first_track:
                client_ym = Client(tokens[str(user_discord)]).init()
                data_servers[interaction.guild.name]['radio'] = Radio(client_ym)
                data_servers[interaction.guild.name]['user_discord_play'] = user_discord
                for rotor in client_ym.rotor_stations_dashboard().stations:
                    if rotor.station['name'] == "Моя волна":
                        station = rotor.station
                _station_id = station_id or f'{station.id.type}:{station.id.tag}'
                _station_from = station_from or station.id_for_from
                track = data_servers[interaction.guild.name]['radio'].start_radio(_station_id, _station_from)
            else:
                track = data_servers[interaction.guild.name]['radio'].play_next()

            data_servers[interaction.guild.name]['track_id_play_now'] = track.id
            data_servers[interaction.guild.name]['track_id_play_now'] = track.duration_ms
            base_url = 'https://music.yandex.ru/track/'
            if ":" in track.track_id:
                data_servers[interaction.guild.name]['track_url'] = base_url + str(track.track_id).split(":")[0]
            else:
                data_servers[interaction.guild.name]['track_url'] = base_url + str(track.track_id)

            if new_task:
                data_servers[interaction.guild.name]['task'] = \
                    asyncio.create_task(play(interaction, data_servers[interaction.guild.name]['track_url']))
                break
            else:
                return data_servers[interaction.guild.name]['track_url']
        except Exception as e:
            if error_count < 2:
                await interaction.channel.send(f'Произошла ошибка: {e}. Подождите')
                await asyncio.sleep(1)
                error_count += 1
            else:
                await interaction.channel.send("Не удалось установить соединение с сервисом Яндекс.Музыка")
                return False


'''
Класс реализации радио
'''
class Radio:
    def __init__(self, client):
        self.client = client
        self.station_id = None
        self.station_from = None

        self.play_id = None
        self.index = 0
        self.current_track = None
        self.station_tracks = None

    def start_radio(self, station_id, station_from) -> Track:
        self.station_id = station_id
        self.station_from = station_from

        # get first 5 tracks
        self.__update_radio_batch(None)

        # setup current track
        self.current_track = self.__update_current_track()
        return self.current_track

    def play_next(self) -> Track:
        # send prev track finalize info
        self.__send_play_end_track(self.current_track, self.play_id)
        self.__send_play_end_radio(self.current_track, self.station_tracks.batch_id)

        # get next index
        self.index += 1
        if self.index >= len(self.station_tracks.sequence):
            # get next 5 tracks. Set index to 0
            self.__update_radio_batch(self.current_track.track_id)

        # setup next track
        self.current_track = self.__update_current_track()
        return self.current_track

    def __update_radio_batch(self, queue=None):
        self.index = 0
        self.station_tracks = self.client.rotor_station_tracks(self.station_id, queue=queue)
        self.__send_start_radio(self.station_tracks.batch_id)

    def __update_current_track(self):
        self.play_id = self.__generate_play_id()
        track = self.client.tracks([self.station_tracks.sequence[self.index].track.track_id])[0]
        self.__send_play_start_track(track, self.play_id)
        self.__send_play_start_radio(track, self.station_tracks.batch_id)
        return track

    def __send_start_radio(self, batch_id):
        self.client.rotor_station_feedback_radio_started(
            station=self.station_id, from_=self.station_from, batch_id=batch_id
        )

    def __send_play_start_track(self, track, play_id):
        total_seconds = track.duration_ms / 1000
        self.client.play_audio(
            from_="desktop_win-home-playlist_of_the_day-playlist-default",
            track_id=track.id,
            album_id=track.albums[0].id,
            play_id=play_id,
            track_length_seconds=0,
            total_played_seconds=0,
            end_position_seconds=total_seconds,
        )

    def __send_play_start_radio(self, track, batch_id):
        self.client.rotor_station_feedback_track_started(station=self.station_id, track_id=track.id, batch_id=batch_id)

    def __send_play_end_track(self, track, play_id):
        # played_seconds = 5.0
        played_seconds = track.duration_ms / 1000
        total_seconds = track.duration_ms / 1000
        self.client.play_audio(
            from_="desktop_win-home-playlist_of_the_day-playlist-default",
            track_id=track.id,
            album_id=track.albums[0].id,
            play_id=play_id,
            track_length_seconds=int(total_seconds),
            total_played_seconds=played_seconds,
            end_position_seconds=total_seconds,
        )

    def __send_play_end_radio(self, track, batch_id):
        played_seconds = track.duration_ms / 1000
        self.client.rotor_station_feedback_track_finished(
            station=self.station_id, track_id=track.id, total_played_seconds=played_seconds, batch_id=batch_id
        )
        pass

    @staticmethod
    def __generate_play_id():
        return "%s-%s-%s" % (int(random() * 1000), int(random() * 1000), int(random() * 1000))


'''
Классы реализации кнопок
'''
class repeat_button(Button):
    def __init__(self):
        super().__init__(style=ButtonStyle.primary, label="Повтор", emoji="🔂", row=2)

    async def callback(self, interaction: discord.Interaction):
        global data_servers
        if self.style == ButtonStyle.green:
            self.style = ButtonStyle.primary  # изменяем стиль кнопки на primary
            data_servers[interaction.guild.name]['repeat_flag'] = False  # устанавливаем repeat_flag в False
        else:
            self.style = ButtonStyle.green  # изменяем стиль кнопки на зеленый
            data_servers[interaction.guild.name]['repeat_flag'] = True  # устанавливаем repeat_flag в True
        await interaction.response.edit_message(view=self.view)  # обновляем стиль кнопки
class next_button(Button):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(style=ButtonStyle.primary,
                         label="К следующему",
                         emoji="⏭️",
                         row=1,
                         disabled=data_servers[interaction.guild.name]['index_play_now'] + 1 >=
                                  len(data_servers[interaction.guild.name]['playlist']) and not
                                  data_servers[interaction.guild.name]['radio_check'] and not
                                  data_servers[interaction.guild.name]['stream_by_track_check'])

    async def callback(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        voice_client.stop()
class prev_button(Button):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(style=ButtonStyle.primary,
                         label="К предыдущему",
                         emoji="⏮️",
                         row=1,
                         disabled=data_servers[interaction.guild.name]['index_play_now'] - 1 < 0 or
                                  data_servers[interaction.guild.name]['radio_check'] or
                                  data_servers[interaction.guild.name]['stream_by_track_check'])

    async def callback(self, interaction: discord.Interaction):
        global data_servers
        voice_client = interaction.guild.voice_client
        voice_client.stop()
        data_servers[interaction.guild.name]['index_play_now'] -= 2
class pause_resume_button(Button):
    def __init__(self):
        super().__init__(style=ButtonStyle.primary, label="Пауза/Продолжить", emoji="⏯️", row=1)

    async def callback(self, interaction):
        voice_client = interaction.guild.voice_client  # use the attribute
        if self.style == ButtonStyle.green:
            self.style = ButtonStyle.primary  # изменяем стиль кнопки на primary
            voice_client.resume()
        else:
            self.style = ButtonStyle.green  # изменяем стиль кнопки на зеленый
            voice_client.pause()
        await interaction.response.edit_message(view=self.view)  # обновляем стиль кнопки
class disconnect_button(Button):
    def __init__(self):
        super().__init__(style=ButtonStyle.red, label="Отключить", emoji="📛", row=3)

    async def callback(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        await disconnect(interaction)
class lyrics_button(Button):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(style=ButtonStyle.primary,
                         label="Текст",
                         emoji="🗒️",
                         row=2,
                         disabled=data_servers[interaction.guild.name]['lyrics'] is None)

    async def callback(self, interaction: discord.Interaction):
        global data_servers
        if self.style == ButtonStyle.green:
            self.style = ButtonStyle.primary  # изменяем стиль кнопки на primary
            async for message in interaction.channel.history():
                if message.author == client.user and message.content.startswith('Текст'):
                    await message.delete()
        else:
            self.style = ButtonStyle.green  # изменяем стиль кнопки на зеленый
            if len(data_servers[interaction.guild.name]['lyrics']) > 2000:
                # Split the lyrics into two parts using textwrap
                parts = textwrap.wrap(data_servers[interaction.guild.name]['lyrics'], width=1800,
                                      break_long_words=False, replace_whitespace=False)
                await interaction.channel.send(f"Текст трека (часть 1):\n{parts[0]}")
                await interaction.channel.send(f"Текст трека (часть 2):\n{parts[1]}")
            else:
                await interaction.channel.send(f"Текст трека:\n{data_servers[interaction.guild.name]['lyrics']}")
        await interaction.response.edit_message(view=self.view)  # обновляем стиль кнопки
class track_url_button(Button):
    def __init__(self, interaction: discord.Interaction):
        if data_servers[interaction.guild.name]['track_url']:
            super().__init__(style=ButtonStyle.url,
                             label="Ссылка",
                             emoji="🌐",
                             url=data_servers[interaction.guild.name]['track_url'],
                             row=2)
        else:
            super().__init__(style=ButtonStyle.grey,
                             label="Ссылка",
                             emoji="🌐",
                             disabled=True,
                             row=2)
class stream_by_track_button(Button):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(style=ButtonStyle.primary,
                         label="Моя волна по треку",
                         emoji="💫",
                         row=2,
                         disabled=not data_servers[interaction.guild.name]['track_id_play_now'])

    async def callback(self, interaction: discord.Interaction):
        global data_servers
        data_servers[interaction.guild.name]['radio_check'] = False
        data_servers[interaction.guild.name]['stream_by_track_check'] = True
        data_servers[interaction.guild.name]['playlist'] = []
        data_servers[interaction.guild.name]['index_play_now'] = 0

        voice_client = interaction.guild.voice_client
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            data_servers[interaction.guild.name]['task'].cancel()
        await play_radio(interaction=interaction,
                         user_discord=data_servers[interaction.guild.name]['user_discord_play'],
                         first_track=True,
                         station_id='track:' + data_servers[interaction.guild.name]['track_id_play_now'],
                         station_from='track',
                         new_task=True)
class PlaylistSelect(Select):
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        options = []
        user_discord = str(interaction.user)
        client_ym = Client(tokens[user_discord]).init()

        options.append(SelectOption(
            label="Продолжить слушать",
            value="1",
            description="Запустить трек, на котором вы остановились")
        )
        options.append(SelectOption(
            label="Моя волна",
            value="2",
            description="Радио")
        )
        options.append(SelectOption(
            label="Мне нравится",
            value="3",
            description=f"Количество треков: {len(client_ym.users_likes_tracks())}")
        )

        # Формируем сообщение со списком плейлистов и их ID
        playlists_ym = client_ym.users_playlists_list()
        for playlist_ym in playlists_ym:
            playlist_ym_id = playlist_ym.playlist_id.split(':')[1]
            options.append(SelectOption(
                label=str(playlist_ym.title),
                value=str(playlist_ym_id),
                description=f"Количество треков: {client_ym.users_playlists(int(playlist_ym_id)).track_count}")
            )

        super().__init__(placeholder='Выберете плейлист...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        global data_servers
        await interaction.response.defer()
        await interaction.edit_original_response(content='Подождите', view=None)
        voice_client = interaction.guild.voice_client

        data_servers[interaction.guild.name]['playlist'] = []
        data_servers[interaction.guild.name]['index_play_now'] = 0

        if self.values[0] == "1":
            user_discord = str(interaction.user)
            client_ym = Client(tokens[user_discord]).init()
            context = client_ym.queues_list()[0].context
            type = context.type
            if type == 'playlist':
                data_servers[interaction.guild.name]['radio_check'] = False
                data_servers[interaction.guild.name]['stream_by_track_check'] = False
                data_servers[interaction.guild.name]['task'] = asyncio.create_task(play(interaction, f"{context.id.split(':')[1]},{int(client_ym.queue(client_ym.queues_list()[0].id).current_index) + 1}"))
                data_servers[interaction.guild.name]['task_reserv'] = data_servers[interaction.guild.name]['task']
                data_servers[interaction.guild.name]['index_play_now'] = client_ym.queue(client_ym.queues_list()[0].id).current_index
            elif type == 'my_music':
                data_servers[interaction.guild.name]['radio_check'] = False
                data_servers[interaction.guild.name]['stream_by_track_check'] = False
                find = False
                for playlist in client_ym.users_playlists_list():
                    playlist_id = playlist.playlist_id.split(':')[1]
                    if str(client_ym.users_playlists(playlist_id).tracks[0].id) == str(client_ym.queue(client_ym.queues_list()[0].id).tracks[0].track_id):
                        find = True
                        break
                if not find:
                    if str(client_ym.users_likes_tracks()[0].id) == str(client_ym.queue(client_ym.queues_list()[0].id).tracks[0].track_id):
                        playlist_id = 3
                data_servers[interaction.guild.name]['task'] = asyncio.create_task(play(interaction, f"{playlist_id},{int(client_ym.queue(client_ym.queues_list()[0].id).current_index) + 1}"))
                data_servers[interaction.guild.name]['task_reserv'] = data_servers[interaction.guild.name]['task']
                data_servers[interaction.guild.name]['index_play_now'] = int(client_ym.queue(client_ym.queues_list()[0].id).current_index)
            elif type == 'radio':
                data_servers[interaction.guild.name]['radio_check'] = True
                data_servers[interaction.guild.name]['stream_by_track_check'] = False
                now = await play_radio(interaction=interaction, station_id=context.id, station_from=context.id.split(':')[0], user_discord=interaction.user, first_track=True)
                data_servers[interaction.guild.name]['task'] = asyncio.create_task(play(interaction, now))
                data_servers[interaction.guild.name]['task_reserv'] = data_servers[interaction.guild.name]['task']
        elif self.values[0] == "2":
            data_servers[interaction.guild.name]['radio_check'] = True
            data_servers[interaction.guild.name]['stream_by_track_check'] = False
            now = await play_radio(interaction=interaction, user_discord=interaction.user, first_track=True)
            data_servers[interaction.guild.name]['task'] = asyncio.create_task(play(interaction, now))
            data_servers[interaction.guild.name]['task_reserv'] = data_servers[interaction.guild.name]['task']
        else:
            data_servers[interaction.guild.name]['radio_check'] = False
            data_servers[interaction.guild.name]['stream_by_track_check'] = False
            data_servers[interaction.guild.name]['task'] = asyncio.create_task(play(interaction, self.values[0]))
            data_servers[interaction.guild.name]['task_reserv'] = data_servers[interaction.guild.name]['task']
class onyourwave_setting_button(Button):
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        super().__init__(style=ButtonStyle.primary,
                         label="Настроить волну",
                         emoji="⚙️",
                         row=3)

    async def callback(self, interaction: discord.Interaction):
        view = View(timeout=1200.0)
        if interaction.user == data_servers[interaction.guild.name]['user_discord_play']:
            view.add_item(onyourwave_setting_diversity(interaction))
            view.add_item(onyourwave_setting_mood_energy(interaction))
            view.add_item(onyourwave_setting_language(interaction))
            embed = discord.Embed(
                title='Настройки волны', color=0xf1ca0d,
                description=f'Характер: {settings_onyourwave[str(interaction.user)]["diversity"]}\n'
                            f'Настроение: {settings_onyourwave[str(interaction.user)]["mood_energy"]}\n'
                            f'Язык: {settings_onyourwave[str(interaction.user)]["language"]}'
            )
            await interaction.response.send_message(view=view, embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message('Настраивать волну может только тот, кто её запустил.', ephemeral=True)
class onyourwave_setting_diversity(Select):
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        super().__init__(placeholder=f'По характеру...', min_values=1, max_values=1, options=[
            SelectOption(label='Любимое', value='favorite', emoji='💖'),
            SelectOption(label='Незнакомое', value='discover', emoji='✨'),
            SelectOption(label='Популярное', value='popular', emoji='⚡'),
            SelectOption(label='По умолчанию', value='default', emoji='♦️')
        ])

    async def callback(self, interaction: discord.Interaction):
        global settings_onyourwave, data_servers
        await interaction.response.defer()
        settings_onyourwave[str(interaction.user)]['diversity'] = self.values[0]

        client_ym = Client(tokens[str(interaction.user)]).init()

        client_ym.rotor_station_settings2(
            station='user:onyourwave',
            mood_energy=settings_onyourwave[str(interaction.user)]['mood_energy'],
            diversity=settings_onyourwave[str(interaction.user)]['diversity'],
            language=settings_onyourwave[str(interaction.user)]['language']
        )
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            data_servers[interaction.guild.name]['task'].cancel()
        await interaction.edit_original_response(content='Подождите')
        await play_radio(interaction=interaction, user_discord=interaction.user, first_track=True, new_task=True)
        embed = discord.Embed(
            title='Настройки волны изменены', color=0xf1ca0d,
            description=f"Характер: {self.values[0]}\n"
                        f"Настроение: {settings_onyourwave[str(interaction.user)]['mood_energy']}\n"
                        f"Язык: {settings_onyourwave[str(interaction.user)]['language']}"
        )
        await interaction.edit_original_response(content='', embed=embed)
class onyourwave_setting_mood_energy(Select):
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        super().__init__(placeholder=f'Под настроение...', min_values=1, max_values=1, options=[
            SelectOption(label='Бодрое', value='active', emoji='🟠'),
            SelectOption(label='Весёлое', value='fun', emoji='🟢'),
            SelectOption(label='Спокойное', value='calm', emoji='🔵'),
            SelectOption(label='Грустное', value='sad', emoji='🟣'),
            SelectOption(label='Любое', value='all', emoji='🔘')
        ])

    async def callback(self, interaction: discord.Interaction):
        global settings_onyourwave, data_servers
        await interaction.response.defer()

        settings_onyourwave[str(interaction.user)]['mood_energy'] = self.values[0]

        client_ym = Client(tokens[str(interaction.user)]).init()

        client_ym.rotor_station_settings2(
            station='user:onyourwave',
            mood_energy=settings_onyourwave[str(interaction.user)]['mood_energy'],
            diversity=settings_onyourwave[str(interaction.user)]['diversity'],
            language=settings_onyourwave[str(interaction.user)]['language']
        )
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            data_servers[interaction.guild.name]['task'].cancel()
        await interaction.edit_original_response(content='Подождите')
        await play_radio(interaction=interaction, user_discord=interaction.user, first_track=True, new_task=True)
        embed = discord.Embed(
            title='Настройки волны изменены', color=0xf1ca0d,
            description=f"Характер: {settings_onyourwave[str(interaction.user)]['diversity']}\n"
                        f"Настроение: {self.values[0]}\n"
                        f"Язык: {settings_onyourwave[str(interaction.user)]['language']}"
        )
        await self.interaction.edit_original_response(content='', embed=embed)
class onyourwave_setting_language(Select):
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        super().__init__(placeholder=f'По языку...', min_values=1, max_values=1, options=[
            SelectOption(label='Русский', value='russian'),
            SelectOption(label='Иностранный', value='not-russian'),
            SelectOption(label='Без слов', value='without-words'),
            SelectOption(label='Любой', value='any')
        ])

    async def callback(self, interaction: discord.Interaction):
        global settings_onyourwave, data_servers
        await interaction.response.defer()

        settings_onyourwave[str(interaction.user)]['language'] = self.values[0]

        client_ym = Client(tokens[str(interaction.user)]).init()

        client_ym.rotor_station_settings2(
            station='user:onyourwave',
            mood_energy=settings_onyourwave[str(interaction.user)]['mood_energy'],
            diversity=settings_onyourwave[str(interaction.user)]['diversity'],
            language=settings_onyourwave[str(interaction.user)]['language']
        )
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            data_servers[interaction.guild.name]['task'].cancel()
        await interaction.edit_original_response(content='Подождите')
        await play_radio(interaction=interaction, user_discord=interaction.user, first_track=True, new_task=True)
        embed = discord.Embed(
            title='Настройки волны изменены', color=0xf1ca0d,
            description=f"Характер: {settings_onyourwave[str(interaction.user)]['diversity']}\n"
                        f"Настроение: {settings_onyourwave[str(interaction.user)]['mood_energy']}\n"
                        f"Язык: {self.values[0]}"
        )
        await interaction.edit_original_response(content='', embed=embed)



'''
Функции для реализации команд
'''
@tree.command(name='play', description="🎧Воспроизвести трек. При вызове без аргумента - воспроизвести плейлист из списка")
@app_commands.rename(url_or_trackname_or_filepath='ссылка_или_название')
@app_commands.describe(url_or_trackname_or_filepath='Вы можете указать: ссылку на трек из Яндекс.Музыки или YouTube, название трека')
async def start_play(interaction: discord.Interaction, url_or_trackname_or_filepath: str = None):
    global data_servers, settings_onyourwave

    await interaction.response.defer(ephemeral=True)

    if interaction.guild.name not in data_servers:
        data_servers[interaction.guild.name] = data_server.copy()

    if str(interaction.user) in tokens:
        client_ym = Client(tokens[str(interaction.user)]).init()
        settings2 = client_ym.rotor_station_info('user:onyourwave')[0]['settings2']
        settings_onyourwave[str(interaction.user)] = {'mood_energy': settings2['mood_energy'],
                                                      'diversity': settings2['diversity'],
                                                      'language': settings2['language']}

    author_voice_state = interaction.user.voice
    if author_voice_state is None:
        await interaction.edit_original_response(content="Подключитесь к голосовому каналу.")
        while not author_voice_state:
            await asyncio.sleep(0.1)
            author_voice_state = interaction.user.voice

    # Проверяем, подключен ли бот к голосовому каналу
    voice_client = interaction.guild.voice_client

    if not voice_client:
        data_servers[interaction.guild.name]['task_check_inactivity'] = asyncio.create_task(
            check_inactivity(interaction))
        data_servers[interaction.guild.name]['task_check_voice_clients'] = asyncio.create_task(
            check_voice_clients(interaction))
        voice_channel = interaction.user.voice.channel
        await voice_channel.connect()
        voice_client = interaction.guild.voice_client
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        data_servers[interaction.guild.name]['task_reserv'].cancel()
        await remove_last_playing_message(interaction)

    if (not url_or_trackname_or_filepath or \
            "youtube.com" not in url_or_trackname_or_filepath) and \
            str(interaction.user) not in tokens:
            await interaction.edit_original_response(
                content=f"Вы не вошли в аккаунт Яндекс.Музыки. Для входа воспользуйтесь командой /authorize")
            return

    data_servers[interaction.guild.name]['task'] = asyncio.create_task(play(interaction, url_or_trackname_or_filepath=url_or_trackname_or_filepath))
    while not voice_client.is_playing():
        await asyncio.sleep(0.1)
    try:
        await interaction.delete_original_response()
    except:
        pass
async def play(interaction: discord.Interaction, url_or_trackname_or_filepath: str = None):
    try:
        global data_servers

        voice_client = interaction.guild.voice_client

        data_servers[interaction.guild.name]['task_reserv'] = data_servers[interaction.guild.name]['task']

        if not url_or_trackname_or_filepath:  # если не передан url
            view = View()
            view.add_item(PlaylistSelect(interaction))
            await interaction.edit_original_response(content='', view=view)
            return

        while True:
            if "youtube.com" in url_or_trackname_or_filepath:
                if "|" not in url_or_trackname_or_filepath:
                    user_discord = interaction.user
                else:
                    p = url_or_trackname_or_filepath.split('|')
                    name_and_discriminator = p[0]  # получаем имя и дискриминатор в формате "Имя#Дискриминатор"

                    user_discord = discord.utils.get(interaction.guild.members,
                                                     name=name_and_discriminator.split("#")[0],
                                                     discriminator=name_and_discriminator.split("#")[
                                                         1])  # ищем участника с заданным именем и дискриминатором
                    url_or_trackname_or_filepath = p[1]

                p = await play_YouTube(url_or_trackname_or_filepath, user_discord, interaction)
                play_now = p[0]
                audio_file_path = p[1]

            elif "music.yandex.ru" in url_or_trackname_or_filepath:
                if "|" not in url_or_trackname_or_filepath:
                    if data_servers[interaction.guild.name]['user_discord_play']:
                        user_discord = data_servers[interaction.guild.name]['user_discord_play']
                    else:
                        user_discord = interaction.user
                else:
                    p = url_or_trackname_or_filepath.split('|')
                    name_and_discriminator = p[0]  # получаем имя и дискриминатор в формате "Имя#Дискриминатор"

                    user_discord = discord.utils.get(interaction.guild.members,
                                                     name=name_and_discriminator.split("#")[0],
                                                     discriminator=name_and_discriminator.split("#")[
                                                         1])  # ищем участника с заданным именем и дискриминатором
                    url_or_trackname_or_filepath = p[1]

                p = await play_Yandex_Music_url(interaction, url_or_trackname_or_filepath, user_discord)
                play_now = p[0]
                audio_file_path = p[1]

            elif ":\\" in url_or_trackname_or_filepath:
                play_now = url_or_trackname_or_filepath
                audio_file_path = url_or_trackname_or_filepath

                # Проверяем, что файл существует
                if not os.path.isfile(audio_file_path):
                    await interaction.response.send_message(f"Файл `{url_or_trackname_or_filepath}` не найден.", ephemeral=True)
                    return

            else:
                if "|" not in url_or_trackname_or_filepath:
                    user_discord = interaction.user
                else:
                    p = url_or_trackname_or_filepath.split('|')
                    name_and_discriminator = p[0]  # получаем имя и дискриминатор в формате "Имя#Дискриминатор"

                    user_discord = discord.utils.get(interaction.guild.members,
                                                     name=name_and_discriminator.split("#")[0],
                                                     discriminator=name_and_discriminator.split("#")[
                                                         1])  # ищем участника с заданным именем и дискриминатором
                    url_or_trackname_or_filepath = p[1]

                p = await play_Yandex_Music_playlist(interaction, url_or_trackname_or_filepath, user_discord)
                if not p:
                    return

                play_now = p[0]
                audio_file_path = p[1]

            data_servers[interaction.guild.name]['queue_repeat'] = audio_file_path
            options = '-loglevel panic'
            audio_source = await discord.FFmpegOpusAudio.from_probe(audio_file_path, options=options)

            # Проигрываем аудио
            voice_client.play(audio_source)

            duration_track = await milliseconds_to_time(data_servers[interaction.guild.name]['duration'])
            start_time = 0

            if not birthdays[str(interaction.user)]:
                await birthday_send(interaction)

            if not data_servers[interaction.guild.name]['repeat_flag']:
                data_servers[interaction.guild.name]['repeat_flag'] = False
                await remove_last_playing_message(interaction)
                view = View(timeout=1200.0)

                view.add_item(prev_button(interaction))
                view.add_item(pause_resume_button())
                view.add_item(next_button(interaction))
                view.add_item(repeat_button())
                view.add_item(lyrics_button(interaction))
                view.add_item(track_url_button(interaction))
                view.add_item(disconnect_button())
                view.add_item(stream_by_track_button(interaction))
                if data_servers[interaction.guild.name]['radio_check']:
                    view.add_item(onyourwave_setting_button(interaction))

                embed = Embed(title="Сейчас играет", description=play_now, color=0xf1ca0d)
                embed.add_field(name=f'00:00 / {duration_track}', value='')
                if data_servers[interaction.guild.name]['radio_check'] or \
                        data_servers[interaction.guild.name]['stream_by_track_check']:
                    embed.set_footer(text=f"{user_discord} запустил волну", icon_url=user_discord.avatar)
                else:
                    embed.set_footer(text=f"{user_discord} запустил трек", icon_url=user_discord.avatar)

                if data_servers[interaction.guild.name]['cover_url']:
                    embed.set_thumbnail(url=data_servers[interaction.guild.name]['cover_url'])
                message = await interaction.channel.send(embed=embed, view=view)
                data_servers[interaction.guild.name]['message_check'] = message

            while voice_client.is_playing() or voice_client.is_paused():
                if voice_client.is_playing():
                    start_time_inaccuracy = datetime.datetime.now()
                    start_time += 1000
                    time_now = await milliseconds_to_time(start_time)
                    embed.clear_fields()
                    embed.add_field(name=f'{time_now} / {duration_track}', value='')
                    await data_servers[interaction.guild.name]['message_check'].edit(embed=embed)
                    data_servers[interaction.guild.name]['last_activity_time'] = datetime.datetime.now()
                    end_time_inaccuracy = datetime.datetime.now()
                await asyncio.sleep(1 - (end_time_inaccuracy - start_time_inaccuracy).microseconds / 1000000)

            if data_servers[interaction.guild.name]['repeat_flag']:
                continue

            elif data_servers[interaction.guild.name]['radio_check'] or data_servers[interaction.guild.name]['stream_by_track_check']:
                url_or_trackname_or_filepath = await play_radio(interaction=interaction, user_discord=user_discord)

            else:
                if data_servers[interaction.guild.name]['index_play_now'] + 1 < len(
                        data_servers[interaction.guild.name]['playlist']):
                    data_servers[interaction.guild.name]['index_play_now'] += 1
                    url_or_trackname_or_filepath = data_servers[interaction.guild.name]['playlist'][data_servers[interaction.guild.name]['index_play_now']]
                else:
                    await interaction.channel.send("Треки в очереди закончились")
                    return

    except Exception as e:
        await interaction.channel.send(f"Произошла ошибка при проигрывании музыки: {e}.")

@start_play.autocomplete('url_or_trackname_or_filepath')
async def search_yandex_music(interaction: discord.Interaction, search: str):
    global tokens
    user_discord = interaction.user
    url_or_trackname_or_filepath = []
    if ("youtube.com" or "music.yandex.ru") not in search:
        if str(user_discord) in tokens:
            client_ym = Client(tokens[str(user_discord)]).init()
            search_result = client_ym.search(search)
            if search_result.tracks.results:
                for item in search_result.tracks.results:
                    artists = ''
                    if item.artists:
                        artists = ' - ' + ', '.join(artist.name for artist in item.artists)
                    url_or_trackname_or_filepath.append(item.title + artists)
    return [app_commands.Choice(name=item, value=item) for item in url_or_trackname_or_filepath ]

@tree.command(name='authorize', description="🔑Авторизация для использования сервиса Яндекс.Музыка")
@app_commands.describe(token='Вам нужно указать свой токен от аккаунта Яндекс.Музыки')
async def authorize(interaction: discord.Interaction, token: str):
    global tokens
    try:
        if str(interaction.user) in tokens:
            await interaction.response.send_message("Вы уже авторизованы 🥰", ephemeral=True)
            return

        client_check = Client(str(token)).init()
    except Exception:
        await interaction.response.send_message("К сожалению ваш токен неправильный 😞", ephemeral=True)
    else:
        await interaction.response.send_message("Вы успешно авторизовались 😍", ephemeral=True)
        user_discord = str(interaction.user)
        tokens[user_discord] = str(token)

        # записываем данные в файл
        with open("tokens.txt", "a") as f:
            f.seek(0, 2)  # перемещаем курсор в конец файла
            f.write(user_discord + " " + str(token) + "\n")

@tree.command(name='log', description="Служебная команда")
@app_commands.describe(server_name='По умоляанию Ваш сервер.')
@app_commands.default_permissions()
async def log(interaction: discord.Interaction, server_name: str = None):
    global data_servers

    if not server_name:
        server_name = interaction.guild.name

    if server_name in data_servers:
        message = ''
        for item in data_servers[server_name]:
            if item == 'lyrics' and data_servers[server_name][item]:
                message += f'{item}: is present\n'
            else:
                message += f'{item}: {data_servers[server_name][item]}\n'

        filename = f'{server_name}_log.txt'
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(message)

        await interaction.response.send_message(file=discord.File(filename), ephemeral=True)

    else:
        await interaction.response.send_message("Такого сервера в логах нет", ephemeral=True)

@log.autocomplete('server_name')
async def autocomplete_log(interaction: discord.Interaction, search: str):
    global data_servers
    return [app_commands.Choice(name=item, value=item) for item in data_servers if search in item]

@tree.command(name='help', description="❓Справка по командам")
async def commands(interaction: discord.Interaction):
    global data_servers
    if interaction.guild.name not in data_servers:
        data_servers[interaction.guild.name] = data_server.copy()
    command = {'/play': 'Имеет необязательный аргумент \'ссылка_или_название\'\n\n'
                        'При вызове команды без аргумента - предложит выбрать плейлист из списка и запустит его\n\n'
                        'В аргумент можно передать:\n'
                        '1. Ссылку на видео YouTube\n'
                        '2. Ссылку на трек Яндекс.Музыки\n'
                        '3. Название трека (При вводе можно выбрать из выпадающего списка)\n',
               '/authorize': 'Имеет обязательный аргумент \'token\'\n\n'
                             'В аргумент нужно передать Ваш токен от аккаунта Яндекс.Музыки\n\n'
                             'Без авторизации Вы не сможете пользоваться Яндекс.Музыкой\n\n'
                             'С инструкцией по получению токена можно ознакимиться здесь:\nhttps://github.com/MarshalX/yandex-music-api/discussions/513\n\n'
                             'Также можно воспользоваться программой, через которую можно войти с помощью Авторизации Яндекса\n\n'
                             'Скачать можно здесь: https://disk.yandex.ru/d/zBhcTwiut1kxJw\n\n'
                             'Примечания для программы:\n'
                             '- Пока доступна версия только для ОС Windows\n'
                             '- Для работы программы необходимо наличие Goole Chrome на вашем устройстве\n'
                             '- Версия программы не финальная и будет дорабатываться '
               }

    class next_command_button(Button):
        def __init__(self, interaction: discord.Interaction):
            super().__init__(style=ButtonStyle.primary, emoji="➡️", disabled=data_servers[interaction.guild.name]['command_now'] + 1 >= len(command))

        async def callback(self, interaction: discord.Interaction):
            global data_servers
            data_servers[interaction.guild.name]['command_now'] += 1
            self.view.clear_items()
            self.view.add_item(prev_command_button(interaction))
            self.view.add_item(next_command_button(interaction))
            await interaction.response.edit_message(
                content=f'Команда {data_servers[interaction.guild.name]["command_now"]+1} из {len(command)}',
                embed=Embed(title='/authorize', description=command['/authorize'], color=0xf1ca0d),
                view=self.view)

    class prev_command_button(Button):
        def __init__(self, interaction: discord.Interaction):
            super().__init__(style=ButtonStyle.primary, emoji="⬅️", disabled=data_servers[interaction.guild.name]['command_now']-1<0)

        async def callback(self, interaction: discord.Interaction):
            global data_servers
            data_servers[interaction.guild.name]['command_now'] -= 1
            self.view.clear_items()
            self.view.add_item(prev_command_button(interaction))
            self.view.add_item(next_command_button(interaction))
            await interaction.response.edit_message(
                content=f'Команда {data_servers[interaction.guild.name]["command_now"]+1} из {len(command)}',
                embed=Embed(title='/play', description=command['/play'], color=0xf1ca0d),
                view=self.view
            )

    view = View(timeout=1200.0)

    view.add_item(prev_command_button(interaction))
    view.add_item(next_command_button(interaction))

    embed = Embed(title='/play', description=command['/play'], color=0xf1ca0d)

    await interaction.response.send_message(content=f'Команда {data_servers[interaction.guild.name]["command_now"]+1} из {len(command)}', embed=embed, view=view)

@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(activity=discord.Activity(name="/help", type=discord.ActivityType.playing))
    print("Ready!")

# Запускаем бота
client.run(YM_token)
