// Actualización automática: la app se mantiene igual a la carpeta sistema\cliente del Servidor.
//
// 1. Cada consulta de estado trae la "huella" de esa carpeta. Si cambió, se pide la lista de archivos
//    con sus huellas y se bajan solo los distintos a la carpeta oculta .actualizacion (junto al .exe).
// 2. Si cambió el .exe, se lo abre en modo --autoprueba: compila todos sus métodos con el .NET de
//    esta PC (así se detecta un "Método no encontrado" ANTES de reemplazar nada) y comprueba que
//    Windows deja abrirlo. Si falla, no se instala y se avisa al Servidor.
// 3. Cuando nadie está usando la app, se renombran los archivos actuales a *.viejo, se ponen los
//    nuevos y se abre la versión nueva (--actualizada), que espera a que la vieja se cierre.
// 4. Si la versión nueva no llega a abrir su ventana, vuelve sola a la anterior y no reintenta esa
//    misma versión.
//
// Cuidado al tocar este archivo: .NET Framework 4.8 no tiene Trim(char), Split(char), Contains(char),
// StartsWith(char)... (mono sí). Usar siempre las versiones con arreglo o con string.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Transcripcion
{
    static class Actualizador
    {
        const string CARPETA_NUEVA = ".actualizacion";
        static readonly char[] Tab = { '\t' };
        static readonly char[] Renglon = { '\n' };
        static readonly Regex RutaValida = new Regex(@"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$");

        public static string ListaHuella;          // huella de la versión ya bajada y probada (null = nada pendiente)
        public static string ListaVersion = "";
        public static bool SoloReiniciar;          // los archivos ya están al día (los cambió otro usuario de Windows)
        public static bool Saliendo;               // la app se cierra para abrir la versión nueva
        public static string UltimoError = "";
        public static event Action Preparada;

        static List<string> listos = new List<string>();
        static bool trabajando, sinPermiso;
        static DateTime proximoIntento = DateTime.MinValue;
        static string shaPropio;
        static readonly List<string[]> avisosPendientes = new List<string[]>();

        static string Staging { get { return Path.Combine(Config.CarpetaPrograma, CARPETA_NUEVA); } }
        static string Marca { get { return Path.Combine(Config.Carpeta, "actualizacion_en_curso.txt"); } }
        static string Fallida { get { return Path.Combine(Config.Carpeta, "actualizacion_fallida.txt"); } }

        // ------------------------------------------------------------ revisar si hay versión nueva
        public static async Task Revisar(string url, string huella, string version)
        {
            if (trabajando || sinPermiso || ListaHuella != null || string.IsNullOrEmpty(huella) || string.IsNullOrEmpty(url)) return;
            if (huella == Config.HuellaApp || huella == Config.HuellaFallida) return;
            if (DateTime.Now < proximoIntento) return;
            trabajando = true;
            try { await Task.Run(() => Preparar(url)).ConfigureAwait(false); }
            catch (Exception ex)
            {
                UltimoError = (ex.InnerException ?? ex).Message;
                proximoIntento = DateTime.Now.AddMinutes(15);
                Registro.Escribir("Actualización: no se pudo preparar (" + UltimoError + "). Se reintenta en 15 minutos.");
            }
            finally { trabajando = false; }
        }

        static void Preparar(string url)
        {
            var r = Servidor.Manifiesto(url).Result;
            if (!r.Ok) throw new Exception(r.Error ?? "sin lista de archivos");
            string huella = r.Texto("huella"), version = r.Texto("version");
            if (huella == "" || huella == Config.HuellaFallida) return;

            // qué archivos son distintos a los de esta carpeta
            var distintos = new List<Dictionary<string, object>>();
            object o;
            var lista = r.Datos.TryGetValue("archivos", out o) ? o as IEnumerable : null;
            if (lista == null) throw new Exception("lista de archivos ilegible");
            foreach (var x in lista)
            {
                var a = x as Dictionary<string, object>;
                if (a == null) continue;
                string rel = a["ruta"] + "", sha = (a["sha256"] + "").ToLowerInvariant();
                if (!RutaValida.IsMatch(rel) || rel.IndexOf("..", StringComparison.Ordinal) >= 0)
                    throw new Exception("ruta no válida en la lista: " + rel);
                string local = Local(rel);
                if (!File.Exists(local) || Sha(local) != sha) distintos.Add(a);
            }

            if (distintos.Count == 0)
            {   // archivos al día; ¿esta ventana sigue siendo la versión vieja?
                if (ExeCambioEnDisco())
                {
                    Registro.Escribir("Actualización: los archivos ya son la versión " + version + "; falta reiniciar la app.");
                    listos = new List<string>(); SoloReiniciar = true;
                    ListaVersion = version; ListaHuella = huella;
                    Avisar();
                }
                else { Config.HuellaApp = huella; Config.GuardarSeguro(); }
                return;
            }

            // carpeta de trabajo junto al .exe (si no se puede escribir, no hay actualización automática)
            try
            {
                if (Directory.Exists(Staging)) Directory.Delete(Staging, true);
                var di = Directory.CreateDirectory(Staging);
                di.Attributes |= FileAttributes.Hidden;
                File.WriteAllText(Path.Combine(Staging, "prueba.txt"), "ok");
            }
            catch (Exception ex)
            {
                sinPermiso = true;
                Registro.Escribir("Actualización: la carpeta de la app no permite escribir (" + ex.Message + ").");
                AvisarAlServidor("no se puede actualizar sola: la carpeta de la app no permite escribir. Hay que copiarla a mano.", "aviso");
                return;
            }

            Registro.Escribir("Actualización: bajando la versión " + version + " (" + distintos.Count + " archivo(s)).");
            var nuevos = new List<string>();
            bool cambiaExe = false;
            foreach (var a in distintos)
            {
                string rel = a["ruta"] + "", sha = (a["sha256"] + "").ToLowerInvariant();
                string destino = Path.Combine(Staging, rel.Replace('/', '\\'));
                Directory.CreateDirectory(Path.GetDirectoryName(destino));
                string err = Servidor.Bajar(url, rel, destino);
                if (err != null) throw new Exception("no pude bajar " + rel + ": " + err);
                if (Sha(destino) != sha) throw new Exception(rel + " llegó dañado");
                nuevos.Add(rel);
                if (string.Equals(rel, "Transcripcion.exe", StringComparison.OrdinalIgnoreCase)) cambiaExe = true;
            }

            if (cambiaExe)
            {
                string detalle;
                if (!Probar(out detalle))
                {
                    Config.HuellaFallida = huella; Config.GuardarSeguro();
                    try { Directory.Delete(Staging, true); } catch { }
                    Registro.Escribir("Actualización: la versión " + version + " NO pasó la prueba en esta PC y no se instala. " + detalle);
                    AvisarAlServidor("la versión " + version + " de la app no pasó la prueba en esta PC y no se instaló (sigue con la " +
                                     Programa.VERSION + "). " + detalle, "aviso");
                    return;
                }
                Registro.Escribir("Actualización: la versión " + version + " pasó la prueba. " + detalle);
            }
            listos = nuevos; SoloReiniciar = false;
            ListaVersion = version; ListaHuella = huella;
            Avisar();
        }

        static void Avisar() { var h = Preparada; if (h != null) h(); }

        static string Local(string rel) { return Path.Combine(Config.CarpetaPrograma, rel.Replace('/', '\\')); }

        public static string Sha(string ruta)
        {
            using (var s = SHA256.Create())
            using (var f = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                return BitConverter.ToString(s.ComputeHash(f)).Replace("-", "").ToLowerInvariant();
        }

        // ¿El .exe que está en la carpeta ya no es el que está corriendo?
        static bool ExeCambioEnDisco()
        {
            try { return shaPropio != null && Sha(Application.ExecutablePath) != shaPropio; }
            catch { return false; }
        }

        public static void AlIniciar()
        {
            try { shaPropio = Sha(Application.ExecutablePath); } catch { }
            LimpiarViejos();
            try
            {   // una versión nueva que no abrió y volvió a esta: no reintentarla
                if (File.Exists(Fallida))
                {
                    var l = File.ReadAllText(Fallida, Encoding.UTF8).Split(Renglon);
                    if (l.Length > 0 && l[0].Trim() != "") { Config.HuellaFallida = l[0].Trim(); Config.GuardarSeguro(); }
                    string ver = l.Length > 1 ? l[1].Trim() : "";
                    string motivo = l.Length > 2 ? l[2].Trim() : "";
                    AvisarAlServidor("la versión " + ver + " de la app no abrió en esta PC (" + motivo + "); volvió sola a la " + Programa.VERSION + ".", "aviso");
                    File.Delete(Fallida);
                }
            }
            catch (Exception ex) { Registro.Escribir("Actualización: " + ex.Message); }
        }

        // ------------------------------------------------------------ prueba antes de instalar
        static bool Probar(out string detalle)
        {
            string exe = Path.Combine(Staging, "Transcripcion.exe");
            string informe = Path.Combine(Staging, "autoprueba.txt");
            try
            {
                var psi = new ProcessStartInfo(exe, "--autoprueba \"" + Config.CarpetaPrograma + "\"")
                { UseShellExecute = false, WorkingDirectory = Staging, CreateNoWindow = true };
                using (var p = Process.Start(psi))
                {
                    if (!p.WaitForExit(90000)) { try { p.Kill(); } catch { } detalle = "La prueba no terminó en 90 segundos."; return false; }
                    string txt = File.Exists(informe) ? File.ReadAllText(informe, Encoding.UTF8).Trim() : "";
                    detalle = txt == "" ? "(sin detalle)" : (txt.Length > 300 ? txt.Substring(0, 300) + "…" : txt);
                    return p.ExitCode == 0;
                }
            }
            catch (Exception ex)
            {   // típico: una política del trabajo que no deja abrir este .exe
                detalle = "Windows no dejó abrir la versión nueva (" + ex.Message + ").";
                return false;
            }
        }

        // La versión nueva corre esto (Transcripcion.exe --autoprueba "carpeta de la app"): compila cada método
        // con el .NET de esta PC. Si falta algo del .NET Framework, acá aparece y no se instala.
        public static int Autoprueba(string carpetaPrograma)
        {
            string aqui = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            var errores = new List<string>();
            int n = 0;
            AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
            {
                string nombre = new AssemblyName(e.Name).Name + ".dll";
                foreach (var c in new[] { aqui, carpetaPrograma })
                {
                    if (string.IsNullOrEmpty(c)) continue;
                    string p = Path.Combine(c, nombre);
                    if (File.Exists(p)) return Assembly.LoadFrom(p);
                }
                return null;
            };
            try
            {
                Type[] tipos;
                try { tipos = Assembly.GetExecutingAssembly().GetTypes(); }
                catch (ReflectionTypeLoadException ex)
                {
                    var t2 = new List<Type>();
                    foreach (var t in ex.Types) if (t != null) t2.Add(t);
                    foreach (var le in ex.LoaderExceptions) if (le != null) errores.Add("Carga: " + le.Message);
                    tipos = t2.ToArray();
                }
                const BindingFlags F = BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic |
                                       BindingFlags.Instance | BindingFlags.Static;
                foreach (var t in tipos)
                {
                    if (t.ContainsGenericParameters) continue;
                    var metodos = new List<MethodBase>();
                    try { metodos.AddRange(t.GetMethods(F)); metodos.AddRange(t.GetConstructors(F)); }
                    catch (Exception ex) { errores.Add(t.FullName + ": " + (ex.InnerException ?? ex).Message); continue; }
                    foreach (var m in metodos)
                    {
                        if (m.IsAbstract || m.ContainsGenericParameters) continue;
                        if ((m.Attributes & MethodAttributes.PinvokeImpl) != 0) continue;
                        var impl = m.GetMethodImplementationFlags();
                        if ((impl & (MethodImplAttributes.InternalCall | MethodImplAttributes.Runtime)) != 0) continue;
                        try
                        {
                            RevisarReferencias(m);                       // cada método o campo que usa, contra este .NET
                            RuntimeHelpers.PrepareMethod(m.MethodHandle); // y compilarlo
                            n++;
                        }
                        catch (Exception ex) { errores.Add(t.Name + "." + m.Name + ": " + (ex.InnerException ?? ex).Message); }
                    }
                }
            }
            catch (Exception ex) { errores.Add("General: " + ex.Message); }
            string res = errores.Count == 0
                ? "Autoprueba OK: " + n + " métodos compilados con .NET " + Environment.Version + "."
                : "Autoprueba con " + errores.Count + " error(es): " + string.Join(" | ", errores.ToArray());
            try { File.WriteAllText(Path.Combine(aqui, "autoprueba.txt"), res, Encoding.UTF8); } catch { }
            return errores.Count == 0 ? 0 : 3;
        }

        // Recorre el código (IL) del método y resuelve cada método, campo o tipo que usa. Si este .NET no lo
        // tiene (por ejemplo string.TrimEnd(char), que existe en mono pero no en .NET Framework 4.8), falla acá.
        static Dictionary<short, OpCode> opcodes;
        static void RevisarReferencias(MethodBase m)
        {
            var cuerpo = m.GetMethodBody();
            if (cuerpo == null) return;
            byte[] il = cuerpo.GetILAsByteArray();
            if (il == null) return;
            if (opcodes == null)
            {
                opcodes = new Dictionary<short, OpCode>();
                foreach (var f in typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static))
                {
                    var oc = f.GetValue(null);
                    if (oc is OpCode) opcodes[((OpCode)oc).Value] = (OpCode)oc;
                }
            }
            Type[] gt = m.DeclaringType != null && m.DeclaringType.IsGenericType ? m.DeclaringType.GetGenericArguments() : null;
            Type[] gm = m.IsGenericMethod ? m.GetGenericArguments() : null;
            int i = 0;
            while (i < il.Length)
            {
                short v = il[i] == 0xFE && i + 1 < il.Length ? (short)(0xFE00 | il[i + 1]) : il[i];
                OpCode op;
                if (!opcodes.TryGetValue(v, out op)) throw new Exception("instrucción desconocida en el código");
                i += op.Size;
                switch (op.OperandType)
                {
                    case OperandType.InlineMethod:
                    case OperandType.InlineField:
                    case OperandType.InlineType:
                    case OperandType.InlineTok:
                        m.Module.ResolveMember(BitConverter.ToInt32(il, i), gt, gm);
                        i += 4; break;
                    case OperandType.InlineNone: break;
                    case OperandType.ShortInlineBrTarget:
                    case OperandType.ShortInlineI:
                    case OperandType.ShortInlineVar: i += 1; break;
                    case OperandType.InlineVar: i += 2; break;
                    case OperandType.InlineI8:
                    case OperandType.InlineR: i += 8; break;
                    case OperandType.InlineSwitch: i += 4 + 4 * BitConverter.ToInt32(il, i); break;
                    default: i += 4; break;      // InlineBrTarget, InlineI, InlineSig, InlineString, ShortInlineR
                }
            }
        }

        // ------------------------------------------------------------ instalar y reabrir
        // Reemplaza los archivos (renombrando los actuales a *.viejo) y abre la versión nueva.
        // Devuelve false si no se pudo; en ese caso todo queda como estaba.
        public static bool AplicarYReabrir(bool oculta)
        {
            var hechos = new List<string[]>();     // {destino, viejo}
            try
            {
                if (!SoloReiniciar)
                {
                    foreach (var rel in listos)
                    {
                        string nuevo = Path.Combine(Staging, rel.Replace('/', '\\'));
                        if (!File.Exists(nuevo)) throw new Exception("falta " + rel + " en la carpeta de la actualización");
                    }
                    foreach (var rel in listos)
                    {
                        string nuevo = Path.Combine(Staging, rel.Replace('/', '\\'));
                        string destino = Local(rel);
                        Directory.CreateDirectory(Path.GetDirectoryName(destino));
                        string viejo = "";
                        if (File.Exists(destino))
                        {
                            viejo = destino + ".viejo";
                            if (File.Exists(viejo)) { try { File.Delete(viejo); } catch { viejo = destino + ".viejo-" + DateTime.Now.Ticks; } }
                            File.Move(destino, viejo);     // Windows deja renombrar un .exe o .dll en uso
                        }
                        hechos.Add(new[] { destino, viejo });
                        File.Move(nuevo, destino);
                    }
                }
                // marca para la versión nueva: si no llega a abrir, vuelve a esta
                var sb = new StringBuilder();
                sb.Append(ListaHuella).Append('\n').Append(ListaVersion).Append('\n').Append(Programa.VERSION).Append('\n')
                  .Append(DateTime.UtcNow.Ticks).Append('\n');
                foreach (var h in hechos) sb.Append(h[0]).Append('\t').Append(h[1]).Append('\n');
                File.WriteAllText(Marca, sb.ToString(), Encoding.UTF8);

                Process.Start(new ProcessStartInfo(Application.ExecutablePath,
                    "--actualizada " + Process.GetCurrentProcess().Id + (oculta ? " --oculta" : "")) { UseShellExecute = false });
                Registro.Escribir("Actualización: instalada la versión " + ListaVersion + "; se abre la app nueva.");
                Saliendo = true;
                return true;
            }
            catch (Exception ex)
            {
                UltimoError = ex.Message;
                Registro.Escribir("Actualización: no se pudo instalar (" + ex.Message + "). Se deja todo como estaba.");
                for (int i = hechos.Count - 1; i >= 0; i--)
                {
                    try
                    {
                        string d = hechos[i][0], v = hechos[i][1];
                        if (File.Exists(d)) File.Move(d, d + ".fallida-" + DateTime.Now.Ticks);
                        if (v != "" && File.Exists(v)) File.Move(v, d);
                    }
                    catch (Exception e2) { Registro.Escribir("Actualización: al volver atrás " + hechos[i][0] + ": " + e2.Message); }
                }
                try { File.Delete(Marca); } catch { }
                if (hechos.Count > 0)
                {   // no se pudo abrir la nueva: no reintentar esta versión
                    Config.HuellaFallida = ListaHuella; Config.GuardarSeguro();
                    AvisarAlServidor("no se pudo instalar la versión " + ListaVersion + " (" + ex.Message + "); sigue con la " + Programa.VERSION + ".", "aviso");
                }
                ListaHuella = null;
                return false;
            }
        }

        // La versión nueva espera a que la vieja termine de cerrarse.
        public static void EsperarQueTermine(string pidTexto)
        {
            int pid;
            if (!int.TryParse(pidTexto, out pid)) return;
            try { using (var p = Process.GetProcessById(pid)) p.WaitForExit(20000); }
            catch { }   // ya se cerró
            Thread.Sleep(800);
        }

        // ¿Hay una actualización que no terminó de abrir? Si es así y pasó un rato, volver a la versión anterior.
        public static bool HayQueVolverAtras()
        {
            try
            {
                if (!File.Exists(Marca)) return false;
                var l = File.ReadAllText(Marca, Encoding.UTF8).Split(Renglon);
                long ticks;
                if (l.Length < 4 || !long.TryParse(l[3].Trim(), out ticks)) return true;
                return (DateTime.UtcNow - new DateTime(ticks, DateTimeKind.Utc)).TotalMinutes > 3;
            }
            catch { return false; }
        }

        // La versión nueva abrió bien: se olvida la marca y se borran los *.viejo que se puedan.
        public static void Confirmar()
        {
            try
            {
                if (!File.Exists(Marca)) return;
                var l = File.ReadAllText(Marca, Encoding.UTF8).Split(Renglon);
                if (l.Length > 0 && l[0].Trim() != "") { Config.HuellaApp = l[0].Trim(); Config.GuardarSeguro(); }
                File.Delete(Marca);
                Registro.Escribir("Actualización: la versión " + Programa.VERSION + " abrió bien.");
            }
            catch (Exception ex) { Registro.Escribir("Actualización: " + ex.Message); }
            LimpiarViejos();
        }

        // Si la versión nueva no pudo abrir: devolver los archivos anteriores y abrir la versión anterior.
        // Lo usa la versión NUEVA desde Main, así que usa lo mínimo posible.
        public static bool VolverAtras(string motivo, string[] args)
        {
            try
            {
                string marca = Path.Combine(Config.Carpeta, "actualizacion_en_curso.txt");
                if (!File.Exists(marca)) return false;
                var l = File.ReadAllText(marca, Encoding.UTF8).Split(Renglon);
                for (int i = 4; i < l.Length; i++)
                {
                    var p = l[i].TrimEnd(new[] { '\r' }).Split(Tab);
                    if (p.Length < 2 || p[0] == "") continue;
                    try
                    {
                        if (File.Exists(p[0])) File.Move(p[0], p[0] + ".fallida-" + DateTime.Now.Ticks);
                        if (p[1] != "" && File.Exists(p[1])) File.Move(p[1], p[0]);
                    }
                    catch { }
                }
                string carpeta = Path.GetDirectoryName(marca);
                File.WriteAllText(Path.Combine(carpeta, "actualizacion_fallida.txt"),
                    (l.Length > 0 ? l[0].Trim() : "") + "\n" + (l.Length > 1 ? l[1].Trim() : "") + "\n" +
                    (motivo ?? "").Replace("\r", " ").Replace("\n", " "), Encoding.UTF8);
                File.Delete(marca);
                bool oculta = args != null && Array.IndexOf(args, "--oculta") >= 0;
                Process.Start(new ProcessStartInfo(Application.ExecutablePath, oculta ? "--oculta" : "") { UseShellExecute = false });
                return true;
            }
            catch { return false; }
        }

        static void LimpiarViejos()
        {
            try
            {
                foreach (var f in Directory.GetFiles(Config.CarpetaPrograma, "*", SearchOption.AllDirectories))
                {
                    string n = Path.GetFileName(f);
                    if (n.IndexOf(".viejo", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        n.IndexOf(".fallida-", StringComparison.OrdinalIgnoreCase) >= 0)
                        try { File.Delete(f); } catch { }     // en uso por otra sesión: se borra la próxima vez
                }
                if (Directory.Exists(Staging) && ListaHuella == null && !trabajando)
                    try { Directory.Delete(Staging, true); } catch { }
            }
            catch { }
        }

        // ------------------------------------------------------------ avisos al Servidor
        public static void AvisarAlServidor(string texto, string tipo)
        {
            lock (avisosPendientes) avisosPendientes.Add(new[] { texto, tipo });
        }

        public static async Task EnviarAvisos(string url)
        {
            string[][] lista;
            lock (avisosPendientes) { lista = avisosPendientes.ToArray(); avisosPendientes.Clear(); }
            foreach (var a in lista)
            {
                var r = await Servidor.Avisar(url, a[0], a[1]).ConfigureAwait(false);
                if (r.Codigo == 0) { lock (avisosPendientes) avisosPendientes.Add(a); }   // sin conexión: más tarde
            }
        }
    }
}
