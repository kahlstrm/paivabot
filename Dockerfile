# syntax=docker/dockerfile:1
FROM python:3.11-slim as build

# Setup ENV variables here (if needed in the future)
# Install pipenv
RUN pip3 install pipenv
# Install python dependencies in /.venv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy
WORKDIR /build
COPY ./prisma/schema.prisma schema.prisma
ENV PATH="/.venv/bin:$PATH"
RUN prisma generate
# Install app into container
FROM python:3.11-slim as runtime
WORKDIR /bot
COPY --from=build /.venv /.venv
COPY --from=build /build /bot
COPY . .
ENV PATH="/.venv/bin:$PATH"
# Create a non-root user and add permission to access /bot folder
RUN useradd botuser && \
  chown botuser /bot
USER botuser

# Run the app
CMD ["python3", "bot.py" ]
