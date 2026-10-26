// Notificaciones de Windows con el ícono nuevo (1.11).
//
// Windows 10/11 muestra los globos del ícono junto al reloj como notificaciones. Arriba de cada una va el
// ícono y el nombre de la aplicación, y Windows los saca de su propia memoria de notificaciones, que quedó
// con el ícono viejo (el de antes de la 1.8): el refresco de la 1.10 arregló la barra de tareas, pero esa
// memoria es otra. Dos cambios:
//  1. La app tiene una identidad propia para Windows (AppUserModelID), registrada en
//     HKCU\Software\Classes\AppUserModelId con el nombre y un PNG del ícono nuevo. Al ser una identidad nueva,
//     Windows no tiene nada guardado para ella y usa ese PNG. Los accesos directos anclados se marcan con la
//     misma identidad para que la barra de tareas no muestre dos botones (el anclado y el de la ventana).
//  2. El globo lleva el ícono de la app en grande (NIIF_USER) en lugar de la "i" de información.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Transcripcion
{
    static class Notificaciones
    {
        // Si alguna vez cambia el ícono otra vez, subir el número: Windows la toma como una app nueva.
        public const string Identidad = "Transcripcion.Informes.2";
        static string NombrePng { get { return "icono_notificaciones_2.png"; } }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        static extern int SetCurrentProcessExplicitAppUserModelID(string id);

        // ------------------------------------------------------------ identidad (antes de abrir cualquier ventana)
        public static void PrepararIdentidad()
        {
            try
            {
                string png = Path.Combine(Config.Carpeta, NombrePng);
                if (!File.Exists(png)) GuardarPng(png);

                using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\AppUserModelId\" + Identidad))
                {
                    k.SetValue("DisplayName", "Transcripción");
                    if (File.Exists(png)) k.SetValue("IconUri", png);
                }

                // Solo los anclados a la barra de tareas importan para no duplicar el botón: si alguno no se pudo
                // marcar, la app sigue con la identidad de siempre (y el ícono de las notificaciones como estaba).
                int marcados, fallidos;
                MarcarAccesos(out marcados, out fallidos);
                if (fallidos > 0)
                {
                    Registro.Escribir("Notificaciones: no se pudo marcar " + fallidos + " acceso(s) anclado(s); se deja la identidad anterior.");
                    return;
                }
                int r = SetCurrentProcessExplicitAppUserModelID(Identidad);
                if (r != 0) { Registro.Escribir("Notificaciones: Windows no aceptó la identidad (" + r + ")."); return; }
                if (Config.IdentidadAlDia != Identidad)
                {
                    Config.IdentidadAlDia = Identidad;
                    Config.GuardarSeguro();
                    Registro.Escribir("Notificaciones: identidad " + Identidad + " con el ícono nuevo (" + marcados + " acceso(s) directo(s) marcados).");
                }
            }
            catch (Exception ex) { Registro.Escribir("Notificaciones: no se pudo preparar el ícono: " + ex.Message); }
        }

        // El ícono de la app como PNG (el tamaño más grande que se pueda leer del .ico).
        static void GuardarPng(string png)
        {
            foreach (int lado in new[] { 256, 128, 64, 48 })
            {
                try
                {
                    using (var ico = new Icon(Estilo.IconoApp(), lado, lado))
                    using (var bmp = ico.ToBitmap())
                    {
                        if (bmp.Width < 48) continue;
                        string tmp = png + ".tmp";
                        bmp.Save(tmp, ImageFormat.Png);
                        if (File.Exists(png)) File.Delete(png);
                        File.Move(tmp, png);
                        return;
                    }
                }
                catch { }
            }
            Registro.Escribir("Notificaciones: no se pudo guardar el PNG del ícono.");
        }

        // Marca con la identidad los accesos directos que abren Transcripcion.exe.
        // fallidos cuenta solo los anclados a la barra de tareas.
        static void MarcarAccesos(out int marcados, out int fallidos)
        {
            marcados = 0; fallidos = 0;
            string anclados = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                @"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar");
            foreach (string lnk in Programa.AccesosDirectos())
            {
                bool esAnclado = lnk.StartsWith(anclados, StringComparison.OrdinalIgnoreCase);
                try
                {
                    if (Marcar(lnk))
                    {
                        marcados++;
                        Programa.AvisarCambio(lnk);
                    }
                }
                catch (Exception ex)
                {
                    if (esAnclado) fallidos++;
                    Registro.Escribir("Notificaciones: no se pudo marcar " + Path.GetFileName(lnk) + ": " + ex.Message);
                }
            }
        }

        [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IPropertyStore
        {
            [PreserveSig] int GetCount(out uint n);
            [PreserveSig] int GetAt(uint i, out ClaveProp k);
            [PreserveSig] int GetValue(ref ClaveProp k, out VariantProp v);
            [PreserveSig] int SetValue(ref ClaveProp k, ref VariantProp v);
            [PreserveSig] int Commit();
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        struct ClaveProp { public Guid fmtid; public uint pid; }

        // PROPVARIANT: solo se usa como texto (VT_LPWSTR). Lugar de sobra para 32 y 64 bits.
        [StructLayout(LayoutKind.Explicit, Size = 24)]
        struct VariantProp
        {
            [FieldOffset(0)] public ushort vt;
            [FieldOffset(8)] public IntPtr p;
        }

        [DllImport("ole32.dll")] static extern int PropVariantClear(ref VariantProp v);

        const ushort VT_LPWSTR = 31;
        static readonly Guid ClaseAccesoDirecto = new Guid("00021401-0000-0000-C000-000000000046");

        // true si se cambió el acceso directo; false si ya tenía la identidad.
        static bool Marcar(string lnk)
        {
            var obj = Activator.CreateInstance(Type.GetTypeFromCLSID(ClaseAccesoDirecto));
            try
            {
                var archivo = (IPersistFile)obj;
                archivo.Load(lnk, 2 /* STGM_READWRITE */);
                var props = (IPropertyStore)obj;
                var clave = new ClaveProp { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };   // PKEY_AppUserModel_ID

                VariantProp actual;
                if (props.GetValue(ref clave, out actual) == 0)
                {
                    string ya = actual.vt == VT_LPWSTR && actual.p != IntPtr.Zero ? Marshal.PtrToStringUni(actual.p) : null;
                    PropVariantClear(ref actual);
                    if (ya == Identidad) return false;
                }

                var nuevo = new VariantProp { vt = VT_LPWSTR, p = Marshal.StringToCoTaskMemUni(Identidad) };
                try
                {
                    int r = props.SetValue(ref clave, ref nuevo);
                    if (r != 0) throw new COMException("SetValue", r);
                    r = props.Commit();
                    if (r != 0) throw new COMException("Commit", r);
                }
                finally { PropVariantClear(ref nuevo); }
                archivo.Save(lnk, true);
                return true;
            }
            finally { Marshal.FinalReleaseComObject(obj); }
        }

        // ------------------------------------------------------------ globo con el ícono de la app
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct DatosIcono
        {
            public int cbSize;
            public IntPtr hWnd;
            public int uID;
            public int uFlags;
            public int uCallbackMessage;
            public IntPtr hIcon;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string szTip;
            public int dwState;
            public int dwStateMask;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szInfo;
            public int uTimeoutOrVersion;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szInfoTitle;
            public int dwInfoFlags;
            public Guid guidItem;
            public IntPtr hBalloonIcon;
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        static extern bool Shell_NotifyIcon(int mensaje, ref DatosIcono datos);

        const int NIM_MODIFY = 1, NIF_INFO = 0x10, NIIF_USER = 4, NIIF_LARGE_ICON = 0x20;
        static Icon icoGrande;
        static readonly FieldInfo campoId = typeof(NotifyIcon).GetField("id", BindingFlags.Instance | BindingFlags.NonPublic);
        static readonly FieldInfo campoVentana = typeof(NotifyIcon).GetField("window", BindingFlags.Instance | BindingFlags.NonPublic);

        // Como NotifyIcon.ShowBalloonTip, pero con el ícono de la app en grande. Si algo falla, el globo de siempre.
        public static void Globo(NotifyIcon n, int ms, string titulo, string texto)
        {
            if (!Config.NotificacionesWindows) return;   // apagadas en Configuración (por defecto, desde la 1.14)
            try
            {
                if (Mostrar(n, ms, titulo, texto)) return;
            }
            catch (Exception ex) { Registro.Escribir("Notificaciones: globo con ícono propio no disponible: " + ex.Message); }
            n.ShowBalloonTip(ms, titulo, texto, ToolTipIcon.Info);
        }

        static bool Mostrar(NotifyIcon n, int ms, string titulo, string texto)
        {
            if (!n.Visible || campoId == null || campoVentana == null) return false;
            var ventana = campoVentana.GetValue(n) as NativeWindow;
            if (ventana == null || ventana.Handle == IntPtr.Zero) return false;
            if (icoGrande == null)
            {
                int lado = Math.Max(32, SystemInformation.IconSize.Width * 2);
                icoGrande = new Icon(Estilo.IconoApp(), lado, lado);
            }
            var d = new DatosIcono
            {
                cbSize = Marshal.SizeOf(typeof(DatosIcono)),
                hWnd = ventana.Handle,
                uID = (int)campoId.GetValue(n),
                uFlags = NIF_INFO,
                szTip = "",
                szInfo = Cortar(texto, 255),
                szInfoTitle = Cortar(titulo, 63),
                uTimeoutOrVersion = ms,
                dwInfoFlags = NIIF_USER | NIIF_LARGE_ICON,
                hBalloonIcon = icoGrande.Handle
            };
            return Shell_NotifyIcon(NIM_MODIFY, ref d);
        }

        static string Cortar(string s, int max)
        {
            s = s ?? "";
            return s.Length > max ? s.Substring(0, max) : s;
        }
    }
}
