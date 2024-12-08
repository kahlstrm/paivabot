# Paivabot - telegram Weather Bot
A simple telegram bot that describes current weather (currently for Otaniemi, Espoo) and predicts the "beautifulness" of the day using previously learnt data.

## Development

For development you need:
- [uv](https://docs.astral.sh/uv/)
- Python 3.13
- A free API key from [OpenWeatherMap](https://openweathermap.org/current)
- A libSQL database (local/remote)
- A TG bot API key


## Production (Docker deployment)

For production you need (or is recommended at least):
- [Docker](https://docs.docker.com/get-docker/)
- A free API key from [OpenWeatherMap](https://openweathermap.org/current)
- A Postgres database (local/remote)
- A TG bot API key

1. Build the image:
        
       docker build -t paivabot .

2. setup environment variables inside `.env`

3. Run the image with `.env` as the env-file:

       docker run -d --env-file .env paivabot
