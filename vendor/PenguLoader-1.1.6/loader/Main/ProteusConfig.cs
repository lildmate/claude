using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;

namespace PenguLoader.Main
{
    // Proteus-only adapter: the loader remains official, but Proteus needs the core
    // activation state mirrored into its existing config.ini.
    internal static class ProteusConfig
    {
        // Proteus passes its config.ini: the desktop user's, which core.dll reads in
        // the League client. This process runs elevated, and when Proteus was
        // elevated with another account, LocalApplicationData is that account's.
        private static string ConfigPath
        {
            get
            {
                var fromProteus = Environment.GetEnvironmentVariable("PROTEUS_CONFIG_PATH");
                if (!string.IsNullOrWhiteSpace(fromProteus))
                    return fromProteus;

                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Rose",  // the data folder core.dll reads (see utils/core/paths.py)
                    "config.ini");
            }
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool WritePrivateProfileString(
            string section,
            string key,
            string value,
            string filePath);

        public static void SetLoaderState(bool active)
        {
            var directory = Path.GetDirectoryName(ConfigPath);
            if (!Directory.Exists(directory))
                Directory.CreateDirectory(directory);

            var loaderPath = active
                ? AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                : string.Empty;

            if (!WritePrivateProfileString("General", "disabled", active ? "0" : "1", ConfigPath) ||
                !WritePrivateProfileString("General", "loaderpath", loaderPath, ConfigPath))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not update Proteus config.ini.");
            }
        }
    }
}
