using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
using System.Text;
using System.Windows.Forms;
using System.Collections.Generic;
using Microsoft.Win32;
[assembly: AssemblyTitle("Beyond Nen Launcher")]
[assembly: AssemblyProduct("Beyond Nen Meditation Macro")]
[assembly: AssemblyDescription("Desktop launcher for Beyond Nen training")]
[assembly: AssemblyCompany("Beyond Nen Project")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]
internal static class Launcher {
    private static string Quote(string value) {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
    private static string Probe(string program, string prefix) {
        try {
            string check="import sys,struct;ok=sys.version_info[:2]==(3,12) and struct.calcsize('P')==8;print(sys.executable if ok else '');sys.exit(0 if ok else 1)";
            ProcessStartInfo info=new ProcessStartInfo(program,prefix+"-c "+Quote(check));
            info.UseShellExecute=false; info.CreateNoWindow=true;
            info.RedirectStandardOutput=true; info.RedirectStandardError=true;
            using (Process p=Process.Start(info)) {
                if (!p.WaitForExit(8000)) { p.Kill(); return null; }
                string path=p.StandardOutput.ReadToEnd().Trim();
                return p.ExitCode==0 && File.Exists(path) ? path : null;
            }
        } catch { return null; }
    }
    private static IEnumerable<string> RegisteredPython() {
        List<string> result=new List<string>();
        foreach (RegistryHive hive in new RegistryHive[]{RegistryHive.CurrentUser,RegistryHive.LocalMachine}) {
            foreach (RegistryView view in new RegistryView[]{RegistryView.Registry64,RegistryView.Registry32}) {
                try {
                    using (RegistryKey root=RegistryKey.OpenBaseKey(hive,view))
                    using (RegistryKey python=root.OpenSubKey(@"Software\Python\PythonCore")) {
                        if (python==null) continue;
                        foreach (string name in python.GetSubKeyNames()) {
                            if (!name.StartsWith("3.12",StringComparison.OrdinalIgnoreCase)) continue;
                            using (RegistryKey install=python.OpenSubKey(name+@"\InstallPath")) {
                                if (install==null) continue;
                                string executable=install.GetValue("ExecutablePath") as string;
                                string directory=install.GetValue("") as string;
                                if (!String.IsNullOrEmpty(executable)) result.Add(executable);
                                if (!String.IsNullOrEmpty(directory)) result.Add(Path.Combine(directory,"python.exe"));
                            }
                        }
                    }
                } catch { }
            }
        }
        string local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        result.Add(Path.Combine(local,@"Programs\Python\Python312\python.exe"));
        result.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),@"Python312\python.exe"));
        return result;
    }
    private static string FindPython(string app) {
        string local=Path.Combine(app,"local-python.txt");
        if (File.Exists(local)) {
            string found=Probe(File.ReadAllText(local).Trim(),"");
            if (found!=null) return found;
        }
        foreach (string candidate in RegisteredPython()) {
            if (!File.Exists(candidate)) continue;
            string found=Probe(candidate,""); if (found!=null) return found;
        }
        string python=Probe("py.exe","-3.12 ");
        if (python==null) python=Probe(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"py.exe"),"-3.12 ");
        if (python==null) python=Probe("python.exe","");
        return python;
    }
    private static string ChoosePython(string app) {
        DialogResult result=MessageBox.Show("A compatible Python installation was not found automatically. If Python 3.12 is already installed, select its python.exe now. No reinstall is required.","Beyond Nen - Select Python",MessageBoxButtons.OKCancel,MessageBoxIcon.Information);
        if (result!=DialogResult.OK) return null;
        using (OpenFileDialog dialog=new OpenFileDialog()) {
            dialog.Title="Select your existing Python 3.12 (64-bit) python.exe";
            dialog.Filter="Python executable (python.exe)|python.exe|Executables (*.exe)|*.exe";
            dialog.CheckFileExists=true;
            if (dialog.ShowDialog()!=DialogResult.OK) return null;
            string python=Probe(dialog.FileName,"");
            if (python==null) {
                MessageBox.Show("That executable is not compatible Python 3.12 (64-bit). Select the correct installation; the README has setup details.","Beyond Nen",MessageBoxButtons.OK,MessageBoxIcon.Information); return null;
            }
            File.WriteAllText(Path.Combine(app,"local-python.txt"),python);
            return python;
        }
    }
    [STAThread]
    private static void Main(string[] args) {
        Application.EnableVisualStyles();
        string root=AppDomain.CurrentDomain.BaseDirectory;
        string app=File.Exists(Path.Combine(root,"bootstrap.py")) ? root : Path.Combine(root,"App");
        try {
            if (!File.Exists(Path.Combine(app,"bootstrap.py"))) {
                MessageBox.Show("The application files could not be found. Keep bootstrap.py beside this launcher, or keep the App folder beside the launchers.","Beyond Nen - Application files missing",MessageBoxButtons.OK,MessageBoxIcon.Information); return;
            }
            string python=FindPython(app);
            if (python==null) python=ChoosePython(app);
            if (python==null) return;
            string guiPython=Path.Combine(Path.GetDirectoryName(python),"pythonw.exe");
            if (!File.Exists(guiPython)) guiPython=python;
#if UPDATE_LAUNCHER
            string mode="--gui-update";
#else
            string mode="--quiet-launch";
#endif
            ProcessStartInfo launch=new ProcessStartInfo(guiPython,Quote(Path.Combine(app,"bootstrap.py"))+" "+mode);
            launch.WorkingDirectory=app; launch.UseShellExecute=false; launch.CreateNoWindow=true;
            Process.Start(launch);
        } catch (Exception ex) {
            try { File.AppendAllText(Path.Combine(app,"LOGS.jsonl"),"{\"event\":\"native_launcher_error\",\"error\":\""+ex.GetType().Name+"\"}"+Environment.NewLine); } catch {}
            MessageBox.Show("The application could not start. Check LOGS.jsonl beside bootstrap.py for details.","Beyond Nen - Startup error",MessageBoxButtons.OK,MessageBoxIcon.Error);
        }
    }
}
