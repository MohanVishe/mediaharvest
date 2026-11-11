# Test-only image: the build image plus a headless Android emulator, using
# the plain AOSP system image (no Google apps or services). Needs KVM:
#   docker build -t mediaharvest-android-emu -f .devcontainer/emulator.Dockerfile .devcontainer
#   docker run --rm --device /dev/kvm --group-add "$(getent group kvm | cut -d: -f3)" \
#     mediaharvest-android-emu emulator -avd test -no-window -no-audio
FROM mediaharvest-android-dev

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpulse0 libnss3 libxcursor1 libxdamage1 \
       libxcomposite1 libxi6 libxtst6 libgl1 libegl1 libdbus-1-3 libxkbfile1 libasound2t64 \
    && rm -rf /var/lib/apt/lists/*
RUN sdkmanager "emulator" "system-images;android-36;default;x86_64" \
    && chown -R ubuntu:ubuntu "${ANDROID_HOME}"
USER ubuntu
RUN echo no | avdmanager create avd -n test -k "system-images;android-36;default;x86_64" -d pixel_7
ENV PATH=${PATH}:/opt/android-sdk/emulator
