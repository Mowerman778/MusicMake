package com.musicmake.recorder;

import de.sciss.jump3r.mp3.BitStream;
import de.sciss.jump3r.mp3.GainAnalysis;
import de.sciss.jump3r.mp3.GetAudio;
import de.sciss.jump3r.mp3.ID3Tag;
import de.sciss.jump3r.mp3.Lame;
import de.sciss.jump3r.mp3.LameGlobalFlags;
import de.sciss.jump3r.mp3.MPEGMode;
import de.sciss.jump3r.mp3.Parse;
import de.sciss.jump3r.mp3.Presets;
import de.sciss.jump3r.mp3.Quantize;
import de.sciss.jump3r.mp3.QuantizePVT;
import de.sciss.jump3r.mp3.Reservoir;
import de.sciss.jump3r.mp3.Takehiro;
import de.sciss.jump3r.mp3.VBRTag;
import de.sciss.jump3r.mp3.Version;
import de.sciss.jump3r.mpg.Common;
import de.sciss.jump3r.mpg.Interface;
import de.sciss.jump3r.mpg.MPGLib;

import java.io.IOException;
import java.io.OutputStream;

/**
 * Constant-bitrate MP3 encoder built on jump3r (a pure-Java port of LAME, LGPL).
 *
 * jump3r's convenience class (lowlevel.LameEncoder) needs javax.sound, which Android
 * lacks, so this wires up the encoder modules directly. Feed it interleaved 16-bit PCM.
 */
public final class Mp3Encoder implements AutoCloseable {
    private final Lame lame = new Lame();
    private final LameGlobalFlags gfp;
    private final OutputStream out;
    private final int channels;
    private int[] left = new int[0];
    private int[] right = new int[0];
    private byte[] mp3 = new byte[0];

    public Mp3Encoder(OutputStream out, int sampleRate, int channels, int kbps) {
        if (channels != 1 && channels != 2) throw new IllegalArgumentException("1 or 2 channels");
        this.out = out;
        this.channels = channels;

        GetAudio gaud = new GetAudio();
        GainAnalysis ga = new GainAnalysis();
        BitStream bs = new BitStream();
        Presets p = new Presets();
        QuantizePVT qupvt = new QuantizePVT();
        Quantize qu = new Quantize();
        VBRTag vbr = new VBRTag();
        Version ver = new Version();
        ID3Tag id3 = new ID3Tag();
        Reservoir rv = new Reservoir();
        Takehiro tak = new Takehiro();
        Parse parse = new Parse();
        MPGLib mpg = new MPGLib();
        Interface intf = new Interface();
        Common common = new Common();

        lame.setModules(ga, bs, p, qupvt, qu, vbr, ver, id3, mpg);
        bs.setModules(ga, mpg, ver, vbr);
        id3.setModules(bs, ver);
        p.setModules(lame);
        qu.setModules(bs, rv, qupvt, tak);
        qupvt.setModules(tak, rv, lame.enc.psy);
        rv.setModules(bs);
        tak.setModules(qupvt);
        vbr.setModules(lame, bs, ver);
        gaud.setModules(parse, mpg);
        parse.setModules(ver, id3, p);
        mpg.setModules(intf, common);
        intf.setModules(vbr, common);

        gfp = lame.lame_init();
        gfp.num_channels = channels;
        gfp.in_samplerate = sampleRate;
        gfp.out_samplerate = sampleRate;
        gfp.mode = channels == 1 ? MPEGMode.MONO : MPEGMode.JOINT_STEREO;
        gfp.brate = kbps;
        gfp.quality = 5; // LAME's default speed/quality trade-off
        gfp.bWriteVbrTag = false; // CBR: no Xing header to patch afterwards
        id3.id3tag_init(gfp);
        gfp.write_id3tag_automatic = false;
        if (lame.lame_init_params(gfp) < 0) {
            throw new IllegalArgumentException(
                    "Unsupported MP3 settings: " + sampleRate + " Hz, " + kbps + " kbps");
        }
    }

    /** Encodes {@code count} 16-bit samples (all channels, interleaved) from {@code pcm}. */
    public void encode(short[] pcm, int count) throws IOException {
        int frames = count / channels;
        if (frames == 0) return;
        if (left.length < frames) {
            left = new int[frames];
            right = new int[frames];
            mp3 = new byte[(int) (1.25 * frames) + 7200]; // LAME's worst-case output size
        }
        for (int i = 0; i < frames; i++) {
            // lame_encode_buffer_int expects full-scale 32-bit samples.
            left[i] = pcm[i * channels] << 16;
            right[i] = (channels == 2 ? pcm[i * channels + 1] : pcm[i]) << 16;
        }
        int n = lame.lame_encode_buffer_int(gfp, left, right, frames, mp3, 0, mp3.length);
        if (n < 0) throw new IOException("MP3 encoder error " + n);
        out.write(mp3, 0, n);
    }

    /** Flushes the last frames and closes the output stream. */
    @Override
    public void close() throws IOException {
        try {
            byte[] tail = new byte[7200];
            int n = lame.lame_encode_flush(gfp, tail, 0, tail.length);
            if (n > 0) out.write(tail, 0, n);
            lame.lame_close(gfp);
        } finally {
            out.close();
        }
    }
}
