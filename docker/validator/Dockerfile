FROM eclipse-temurin:21-jre AS validator-jar
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN curl -L -o /opt/validator_cli.jar \
    https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar

FROM node:20-slim AS ig-build
WORKDIR /ig
RUN npm install -g fsh-sushi
COPY fhir-ig/ .
RUN sushi build .

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
COPY --from=validator-jar /opt/validator_cli.jar /opt/validator_cli.jar
COPY --from=ig-build /ig/fsh-generated/resources /ig/output
WORKDIR /srv
COPY docker/validator/server.py .
RUN pip3 install --no-cache-dir --break-system-packages fastapi uvicorn
EXPOSE 8090
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
