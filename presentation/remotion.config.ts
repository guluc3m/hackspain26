import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setConcurrency(2);   // no pisar a llama-server (8 cores compartidos)
Config.setChromiumOpenGlRenderer("angle");
