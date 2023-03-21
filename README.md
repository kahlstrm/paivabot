# Paivabot - telegram Weather Bot
A simple telegram bot that describes current weather (currently for Otaniemi, Espoo) and predicts the "beautifulness" of the day using previously learnt data.

## Development
Currently only works on x86 only because of Prisma binaries (tested on Linux)

For development you need:
- [pipenv](https://pipenv.pypa.io/en/latest/)
- Python 3.11 is required in the Pipfile, highly recommended
- A free API key from [OpenWeatherMap](https://openweathermap.org/current)
- A Postgres database (local/remote)
- A TG bot API key

1. Install dependencies:

       pipenv install --dev
2. setup environment variables inside `.env`
3. generate Prisma binaries:

       pipenv run generate
4. setup database:

       pipenv run db push
5. to start dev environment run:
      
       pipenv run dev

## Production

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
