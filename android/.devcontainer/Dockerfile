# Build container for the MediaHarvest Android app: JDK 21 and the Android
# SDK. Gradle itself comes from the project's wrapper (checksum-pinned).
FROM eclipse-temurin:21.0.8_9-jdk-noble

ARG CMDLINE_TOOLS=16111833
ARG CMDLINE_TOOLS_SHA1=e025545c62a8e64c7559119566a569fb1dec5f60

ENV ANDROID_HOME=/opt/android-sdk
ENV PATH=${PATH}:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools

RUN apt-get update \
    && apt-get install -y --no-install-recommends unzip git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLo /tmp/tools.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
    && echo "${CMDLINE_TOOLS_SHA1}  /tmp/tools.zip" | sha1sum -c - \
    && mkdir -p "${ANDROID_HOME}/cmdline-tools" \
    && unzip -q /tmp/tools.zip -d /tmp/tools \
    && mv /tmp/tools/cmdline-tools "${ANDROID_HOME}/cmdline-tools/latest" \
    && rm -rf /tmp/tools /tmp/tools.zip

# sdkmanager checks each package against Google's published checksum.
RUN yes | sdkmanager --licenses > /dev/null \
    && sdkmanager "platforms;android-37.0" "build-tools;36.0.0" "platform-tools" \
    && chown -R ubuntu:ubuntu "${ANDROID_HOME}" \
    && mkdir -p /home/ubuntu/.gradle && chown ubuntu:ubuntu /home/ubuntu/.gradle

USER ubuntu
WORKDIR /workspace/android
