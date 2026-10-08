package com.zone.lesoongen.domain.shared;

import java.security.SecureRandom;
import java.time.Clock;

public final class Ulids {
    private static final char[] ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ".toCharArray();
    private static final SecureRandom RANDOM = new SecureRandom();

    private Ulids() {
    }

    public static String next(Clock clock) {
        byte[] bytes = new byte[16];
        long timestamp = clock.millis();
        bytes[0] = (byte) (timestamp >>> 40);
        bytes[1] = (byte) (timestamp >>> 32);
        bytes[2] = (byte) (timestamp >>> 24);
        bytes[3] = (byte) (timestamp >>> 16);
        bytes[4] = (byte) (timestamp >>> 8);
        bytes[5] = (byte) timestamp;
        byte[] random = new byte[10];
        RANDOM.nextBytes(random);
        System.arraycopy(random, 0, bytes, 6, random.length);

        char[] output = new char[26];
        int buffer = 0;
        int bits = 2;
        int byteIndex = 0;
        for (int index = 0; index < output.length; index++) {
            while (bits < 5) {
                buffer = (buffer << 8) | (bytes[byteIndex++] & 0xff);
                bits += 8;
            }
            bits -= 5;
            output[index] = ALPHABET[(buffer >>> bits) & 31];
        }
        return new String(output);
    }
}
