from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.editor import VideoFileClip
import os
import assemblyai as aai
from dotenv import load_dotenv
# import openai
import requests
import time
from gtts import gTTS
from pydub import AudioSegment
import boto3
import io


load_dotenv()

OPEN_AI_KEY = os.getenv('OPENAI_API_KEY')

AZURE_ENDPOINT_URL = os.getenv('AZURE_ENDPOINT_URL')

ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')

aai.settings.api_key = ASSEMBLYAI_API_KEY

def getVideoFileInput(file_path):
    # file_path = input("Give the input file path")
    # file_name = ''
    # if '/' in file_path :
    #     t = file_path.split('/')
    #     file_name = t[len(t)-1].split('.')[0]
    # else :
    #     file_name = file_path.split('.')[0]
    file_name = os.path.splitext(os.path.basename(file_path))[0]

    return file_path , file_name

def extractAudioFromVideo(videoFilePath , videoFileName) :
    video = VideoFileClip(videoFilePath)
    # audioFilePath =  os.path.splitext(videoFilePath)[0] + '.wav'
    audioFilePath = './audio/' + videoFileName + '.wav'
    video.audio.write_audiofile(audioFilePath)
    video.close()
    return audioFilePath



def extractTextFromAudio(audio_file_path) :
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file_path)

    timestamped_text = []
    for word in transcript.words :
        timestamped_text.append(
            {
                'text' : word.text,
                'start' : word.start ,
                'end' : word.end,
            }
        )

    return transcript.text , timestamped_text





def correct_transcription(full_text , original_words_timed):
    headers = {
        "Content-Type": "application/json",
        "api-key": OPEN_AI_KEY
    }
    data = {
        "messages" : [
            {'role':'system','content' : 'Improve the grammar and clarity of the text while keeping the same meaning and length of words. Maintain the same basic structure.'},
            {'role' : 'user' , 'content' : full_text }
        ],
        'max_tokens' : 500 ,
    }
    response = requests.post(str(AZURE_ENDPOINT_URL) , headers = headers, json = data)

    if response.status_code != 200 :
        print(response.json())
        return

    result = response.json()
    improved_text = result["choices"][0]["message"]["content"].strip()
    improved_words = improved_text.split()


    improved_words_timed = []
    for i in range(len(improved_words)):
        if i < len(original_words_timed):

            improved_words_timed.append({
                'text': improved_words[i],
                'start': original_words_timed[i]['start'],
                'end': original_words_timed[i]['end']
            })
        else:

            last_timing = original_words_timed[-1]
            improved_words_timed.append({
                'text': improved_words[i],
                'start': last_timing['end'] + 100,  # Add small gap
                'end': last_timing['end'] + 400     # Approximate duration
            })

    return improved_text, improved_words_timed


polly_client = boto3.client('polly')



def final_combine_audio_video(video_path , audio_path  , video_name) :
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)

    new_video = video.set_audio(audio)

    output_path = f'./final_video/{video_name}'
    new_video.write_videofile(output_path,codec="libx264", audio_codec="aac")
    print(f"Video saved at {output_path}")

def create_audio_from_timed_words_polly2(word_timmings, file_name, voice_id='Joey'):
    output_path = f'./fixed_audio/{file_name}_fixed_audio.mp3'
    combined_audio = AudioSegment.silent(duration=0)


    first_start = word_timmings[0]['start']
    normalized_timings = [{
        'text': word['text'],
        'start': word['start'] - first_start,
        'end': word['end'] - first_start
    } for word in word_timmings]


    for i in range(0, len(normalized_timings), 3):

        word_group = normalized_timings[i:i + 3]

        try:

            group_text = ' '.join(word['text'] for word in word_group)


            group_audio = AudioSegment.from_file(
                io.BytesIO(create_speech2(group_text, voice_id=voice_id)),
                format='mp3'
            )


            group_start = word_group[0]['start']
            current_length = len(combined_audio)

            if group_start > current_length:
                silence_needed = group_start - current_length
                combined_audio += AudioSegment.silent(duration=silence_needed)

            combined_audio += group_audio

        except Exception as e:
            print(f"Error processing words: {group_text}")
            print(f"Error details: {str(e)}")
            continue


    combined_audio.export(output_path, format='mp3')
    return output_path

def create_speech2(text, voice_id='Joey', output_format='mp3'):
    try:
        response = polly_client.synthesize_speech(
            Text=text,
            VoiceId=voice_id,
            OutputFormat=output_format
        )
        return response['AudioStream'].read()
    except Exception as e:
        print(f"Error synthesizing speech for text: {text}")
        print(f"Error details: {str(e)}")
        raise


def main() :
    video_path,video_name = getVideoFileInput('./video/video1cut.mp4')
    # print(video_path , video_name)
    audio_path =  extractAudioFromVideo(video_path , video_name)
    original_audio_text , words_timed = extractTextFromAudio(audio_path)
    improved_text , improved_words_timed = correct_transcription(full_text= original_audio_text , original_words_timed=words_timed)
    new_audio_path = create_audio_from_timed_words_polly2(word_timmings=improved_words_timed , file_name='video1cut')
    final_combine_audio_video('./video/video1cut.mp4' , new_audio_path , 'video1cut.mp4')




if __name__ == '__main__' :
    main()
