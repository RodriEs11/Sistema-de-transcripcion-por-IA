// Autocorrección de Word de ESTA PC: lee las entradas con formato del Normal.dotm del usuario de Windows
// (las de Archivo > Opciones > Revisión > Autocorrección marcadas "Con formato") y se las pasa a la
// pantalla del Servidor, que las aplica en el editor del informe al escribir. La lista nunca va al Servidor.
//
// El Normal.dotm es un ZIP. Las entradas están en word/glossary/document.xml, como <w:docPart> con
// <w:type w:val="autoExp"/>; el nombre (<w:name w:val="ECOABD"/>) es lo que se escribe y el cuerpo es lo
// que se inserta. Se lee aunque Word esté abierto (se copia a memoria) y se vuelve a leer si cambia.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;   // DeflateStream (está en System.dll)
using System.Text;
using System.Xml;
using Microsoft.Win32;

namespace Transcripcion
{
    static class Autocorreccion
    {
        const string W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

        public static List<Dictionary<string, object>> Entradas = new List<Dictionary<string, object>>();
        public static string Archivo = "";        // de dónde se leyó ("" si no hay)
        public static string Error = "";          // por qué no se pudo leer ("" si está bien)
        static string firma = null;               // tamaño + fecha del archivo leído

        // Busca el Normal.dotm: la carpeta de plantillas que Word tenga configurada o la de siempre.
        public static string Ruta()
        {
            var carpetas = new List<string>();
            foreach (var ver in new[] { "16.0", "15.0", "14.0" })
            {
                try
                {
                    using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Office\" + ver + @"\Word\Options"))
                    {
                        var v = k == null ? null : k.GetValue("USER-DOTS") as string;
                        if (!string.IsNullOrEmpty(v)) carpetas.Add(Environment.ExpandEnvironmentVariables(v));
                    }
                }
                catch { }
            }
            carpetas.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), @"Microsoft\Templates"));
            foreach (var c in carpetas)
            {
                try { var r = Path.Combine(c, "Normal.dotm"); if (File.Exists(r)) return r; } catch { }
            }
            return "";
        }

        // Vuelve a leer si el archivo cambió (o si se pide forzar). Devuelve true si la lista cambió.
        public static bool Revisar(bool forzar)
        {
            string ruta = Ruta();
            string f = "";
            if (ruta != "")
            {
                try { var fi = new FileInfo(ruta); f = ruta + "|" + fi.Length + "|" + fi.LastWriteTimeUtc.Ticks; }
                catch { f = ""; }
            }
            if (!forzar && f == firma) return false;
            firma = f;
            if (ruta == "")
            {
                bool habia = Entradas.Count > 0 || Archivo != "";
                Entradas = new List<Dictionary<string, object>>(); Archivo = ""; Error = "No hay Normal.dotm en esta PC.";
                return habia || forzar;
            }
            try
            {
                Entradas = Leer(LeerBytes(ruta));
                Archivo = ruta; Error = "";
                Registro.Escribir("Autocorrección de Word: " + Entradas.Count + " entradas leídas de " + ruta);
            }
            catch (Exception ex)
            {
                Error = "No se pudo leer el Normal.dotm: " + ex.Message;
                firma = null;     // se vuelve a intentar en la próxima revisión
                Registro.Escribir(Error);
                return false;     // se queda con la lista anterior
            }
            return true;
        }

        static byte[] LeerBytes(string ruta)
        {
            for (int intento = 0; ; intento++)
            {
                try
                {
                    using (var fs = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                    using (var ms = new MemoryStream())
                    {
                        fs.CopyTo(ms);
                        return ms.ToArray();
                    }
                }
                catch (IOException)
                {
                    if (intento >= 2) throw;
                    System.Threading.Thread.Sleep(300);
                }
            }
        }

        public static List<Dictionary<string, object>> Leer(byte[] datos)
        {
            var lista = new List<Dictionary<string, object>>();
            var vistos = new HashSet<string>();
            byte[] xml = ArchivoDelZip(datos, "word/glossary/document.xml");
            if (xml == null) return lista;     // sin autocorrecciones con formato
            {
                var doc = new XmlDocument { XmlResolver = null };
                var conf = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null };
                using (var r = XmlReader.Create(new MemoryStream(xml), conf)) doc.Load(r);
                var ns = new XmlNamespaceManager(doc.NameTable);
                ns.AddNamespace("w", W);
                foreach (XmlElement part in doc.SelectNodes("//w:docPart", ns))
                {
                    if (part.SelectSingleNode("w:docPartPr/w:types/w:type[@w:val='autoExp']", ns) == null) continue;
                    var nom = part.SelectSingleNode("w:docPartPr/w:name", ns) as XmlElement;
                    string gatillo = nom == null ? "" : nom.GetAttribute("val", W);
                    if (gatillo == "" || gatillo.Length > 100 || vistos.Contains(gatillo)) continue;
                    var pars = new List<object>();
                    int letras = 0;
                    foreach (XmlElement p in part.SelectNodes("w:docPartBody//w:p", ns))
                    {
                        if (p.SelectSingleNode("ancestor::w:p", ns) != null) continue;   // párrafos dentro de cuadros de texto
                        var par = Parrafo(p, ns);
                        letras += ((string)par["t"]).Length;
                        pars.Add(par);
                    }
                    // el último párrafo vacío es la marca de fin del bloque: Word no lo inserta
                    if (pars.Count > 1 && ((string)((Dictionary<string, object>)pars[pars.Count - 1])["t"]) == "") pars.RemoveAt(pars.Count - 1);
                    if (pars.Count == 0 || letras == 0) continue;
                    vistos.Add(gatillo);
                    lista.Add(new Dictionary<string, object> { { "g", gatillo }, { "p", pars } });
                }
            }
            return lista;
        }

        // Un archivo de adentro del ZIP (el .dotm). Se lee a mano con el directorio central del ZIP y
        // DeflateStream, para no depender de System.IO.Compression.dll (ZipArchive).
        public static byte[] ArchivoDelZip(byte[] z, string nombre)
        {
            int fin = -1;
            for (int i = z.Length - 22; i >= 0 && i >= z.Length - 22 - 65535; i--)
                if (U32(z, i) == 0x06054b50) { fin = i; break; }
            if (fin < 0) throw new InvalidDataException("no es un archivo de Word válido");
            int cant = U16(z, fin + 10);
            long pos = U32(z, fin + 16);
            for (int k = 0; k < cant; k++)
            {
                if (pos + 46 > z.Length || U32(z, (int)pos) != 0x02014b50) throw new InvalidDataException("archivo de Word dañado");
                int p = (int)pos;
                int metodo = U16(z, p + 10);
                long comp = U32(z, p + 20), tam = U32(z, p + 24);
                int ln = U16(z, p + 28), le = U16(z, p + 30), lc = U16(z, p + 32);
                long local = U32(z, p + 42);
                string n = Encoding.UTF8.GetString(z, p + 46, ln).Replace('\\', '/');
                pos = p + 46 + ln + le + lc;
                if (!string.Equals(n, nombre, StringComparison.OrdinalIgnoreCase)) continue;
                int l = (int)local;
                if (l + 30 > z.Length || U32(z, l) != 0x04034b50) throw new InvalidDataException("archivo de Word dañado");
                int ini = l + 30 + U16(z, l + 26) + U16(z, l + 28);
                if (ini + comp > z.Length || tam > 50000000) throw new InvalidDataException("archivo de Word dañado");
                if (metodo == 0)
                {
                    var b = new byte[tam]; Array.Copy(z, ini, b, 0, (int)tam); return b;
                }
                if (metodo != 8) throw new InvalidDataException("compresión no soportada");
                using (var ds = new DeflateStream(new MemoryStream(z, ini, (int)comp), CompressionMode.Decompress))
                using (var ms = new MemoryStream())
                {
                    ds.CopyTo(ms);
                    return ms.ToArray();
                }
            }
            return null;
        }

        static int U16(byte[] b, int i) { return b[i] | (b[i + 1] << 8); }
        static uint U32(byte[] b, int i) { return (uint)(b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)); }

        static Dictionary<string, object> Parrafo(XmlElement p, XmlNamespaceManager ns)
        {
            string a = "";
            var jc = p.SelectSingleNode("w:pPr/w:jc", ns) as XmlElement;
            if (jc != null)
            {
                string v = jc.GetAttribute("val", W);
                if (v == "center") a = "center";
                else if (v == "right" || v == "end") a = "right";
                else if (v == "both" || v == "distribute") a = "justify";
            }
            var runs = new List<Dictionary<string, object>>();
            foreach (XmlElement r in p.SelectNodes(".//w:r", ns))
            {
                if (r.SelectSingleNode("ancestor::w:r", ns) != null) continue;
                var t = new StringBuilder();
                TextoDe(r, t);
                string texto = t.ToString().Replace('\u00A0', ' ');
                if (texto == "") continue;
                bool b = Activo(r, "w:rPr/w:b", ns), i = Activo(r, "w:rPr/w:i", ns), u = false;
                var ue = r.SelectSingleNode("w:rPr/w:u", ns) as XmlElement;
                if (ue != null) { string v = ue.GetAttribute("val", W); u = v != "none" && v != ""; }
                string c = "";
                var ce = r.SelectSingleNode("w:rPr/w:color", ns) as XmlElement;
                if (ce != null)
                {
                    string v = ce.GetAttribute("val", W).ToUpperInvariant();
                    if (v.Length == 6 && v != "000000" && EsHex(v)) c = "#" + v;
                }
                var ant = runs.Count > 0 ? runs[runs.Count - 1] : null;
                if (ant != null && (bool)ant["b"] == b && (bool)ant["i"] == i && (bool)ant["u"] == u && (string)ant["c"] == c)
                    ant["t"] = (string)ant["t"] + texto;
                else
                    runs.Add(new Dictionary<string, object> { { "t", texto }, { "b", b }, { "i", i }, { "u", u }, { "c", c } });
            }
            // el editor no guarda espacios al final del renglón
            while (runs.Count > 0)
            {
                var ult = runs[runs.Count - 1];
                string s = ((string)ult["t"]).TrimEnd();
                if (s == "") { runs.RemoveAt(runs.Count - 1); continue; }
                ult["t"] = s; break;
            }
            var sb = new StringBuilder();
            foreach (var x in runs) sb.Append((string)x["t"]);
            return new Dictionary<string, object> { { "t", sb.ToString() }, { "a", a }, { "r", runs } };
        }

        // Texto de un run. Los emojis vienen como <mc:AlternateContent>: <mc:Choice> con <w16se:symEx>
        // y <mc:Fallback> con el carácter en <w:t>; se usa el Fallback.
        static void TextoDe(XmlNode r, StringBuilder t)
        {
            foreach (XmlNode n in r.ChildNodes)
            {
                if (n.LocalName == "AlternateContent")
                {
                    XmlNode fb = null;
                    foreach (XmlNode h in n.ChildNodes) if (h.LocalName == "Fallback") { fb = h; break; }
                    if (fb != null) TextoDe(fb, t);
                    continue;
                }
                if (n.NamespaceURI != W) continue;
                if (n.LocalName == "t") t.Append(n.InnerText);
                else if (n.LocalName == "tab") t.Append(' ');
                else if (n.LocalName == "br" || n.LocalName == "cr") t.Append(' ');
                else if (n.LocalName == "noBreakHyphen") t.Append('-');
                else if (n.LocalName == "sym") t.Append(Simbolo((XmlElement)n));
            }
        }

        static bool Activo(XmlElement r, string ruta, XmlNamespaceManager ns)
        {
            var e = r.SelectSingleNode(ruta, ns) as XmlElement;
            if (e == null) return false;
            string v = e.GetAttribute("val", W);
            return v != "0" && v != "false" && v != "off";
        }

        static bool EsHex(string s)
        {
            foreach (char ch in s) if (!((ch >= '0' && ch <= '9') || (ch >= 'A' && ch <= 'F'))) return false;
            return true;
        }

        // Los símbolos de Wingdings que usa Word en sus autocorrecciones de fábrica, como caracteres comunes
        // (el editor y el Word del informe usan Tahoma, no Wingdings).
        static string Simbolo(XmlElement s)
        {
            string fuente = s.GetAttribute("font", W);
            string cod = s.GetAttribute("char", W).ToUpperInvariant();
            int n;
            if (!int.TryParse(cod, System.Globalization.NumberStyles.HexNumber, System.Globalization.CultureInfo.InvariantCulture, out n)) return "";
            if (fuente.StartsWith("Wingdings", StringComparison.OrdinalIgnoreCase))
            {
                switch (n & 0xFF)
                {
                    case 0xDF: return "←";   // <--
                    case 0xE0: return "→";   // -->
                    case 0xE7: return "⇐";   // <==
                    case 0xE8: return "⇒";   // ==>
                    case 0xF3: return "⇔";   // <=>
                    case 0x4A: return "☺";
                    case 0x4B: return "☹";
                    case 0x4C: return "☹";
                    case 0xFC: return "✓";
                    case 0xFB: return "✗";
                    default: return "";
                }
            }
            if (n >= 0xF000) return "";    // otra fuente de símbolos: no hay equivalente seguro
            return ((char)n).ToString();
        }

        // Lo que se le pasa a la pantalla.
        public static string Json()
        {
            var d = new Dictionary<string, object>
            {
                { "entradas", Entradas },
                { "archivo", Archivo },
                { "error", Error }
            };
            return Config.Json.Serialize(d);
        }
    }
}
