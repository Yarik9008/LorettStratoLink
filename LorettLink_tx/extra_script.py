"""Build script: include FatFs R0.12c middleware from STM32Cube framework."""
import os
Import("env")

framework_dir = env.PioPlatform().get_package_dir("framework-stm32cubef4")
fatfs_dir = os.path.join(framework_dir, "Middlewares", "Third_Party", "FatFs", "src")

if os.path.isdir(fatfs_dir):
    env.Append(CPPPATH=[fatfs_dir])
    env.BuildSources(
        os.path.join("$BUILD_DIR", "FatFs"),
        fatfs_dir,
        src_filter=["+<ff.c>"],
    )
