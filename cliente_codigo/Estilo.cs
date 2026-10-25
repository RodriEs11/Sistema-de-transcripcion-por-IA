// Colores, letras e íconos (los mismos de la interfaz web).
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Transcripcion
{
    static class Estilo
    {
        public static readonly Color Fondo = Color.FromArgb(0xf3, 0xf2, 0xef);
        public static readonly Color Panel = Color.FromArgb(0xfb, 0xfb, 0xfa);
        public static readonly Color Borde = Color.FromArgb(0xcf, 0xcd, 0xc6);
        public static readonly Color Linea = Color.FromArgb(0xe0, 0xdf, 0xda);
        public static readonly Color Texto = Color.FromArgb(0x1d, 0x1d, 0x1b);
        public static readonly Color TextoSuave = Color.FromArgb(0x5c, 0x5b, 0x55);
        public static readonly Color Azul = Color.FromArgb(0x1f, 0x5f, 0xbf);
        public static readonly Color Verde = Color.FromArgb(0x2e, 0x7d, 0x4f);
        public static readonly Color Ambar = Color.FromArgb(0x8a, 0x65, 0x00);
        public static readonly Color Naranja = Color.FromArgb(0xc7, 0x77, 0x00);
        public static readonly Color Rojo = Color.FromArgb(0xb3, 0x26, 0x1e);
        public static readonly Color FondoAmbar = Color.FromArgb(0xff, 0xf6, 0xdc);
        public static readonly Color FondoRojo = Color.FromArgb(0xfd, 0xec, 0xea);
        public static readonly Color Oscuro = Color.FromArgb(0x1d, 0x1d, 0x1b);

        public static readonly Font Fuente = new Font("Segoe UI", 9.75f);
        public static readonly Font Negrita = new Font("Segoe UI", 9.75f, FontStyle.Bold);
        public static readonly Font Chica = new Font("Segoe UI", 8.75f);
        public static readonly Font Titulo = new Font("Segoe UI", 15f, FontStyle.Bold);
        public static readonly Font Mono = new Font("Consolas", 9f);

        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr h);

        // Ícono de la app (diseño "Marcas de revisión", versión 1.8): app.ico va incrustado en el .exe
        // como recurso "Transcripcion.app.ico" (ver compilar.sh y Transcripcion.csproj).
        static Icon icoApp;
        public static Icon IconoApp()
        {
            if (icoApp != null) return icoApp;
            try
            {
                using (var s = typeof(Estilo).Assembly.GetManifestResourceStream("Transcripcion.app.ico"))
                    if (s != null) icoApp = new Icon(s);
            }
            catch { icoApp = null; }
            return icoApp ?? (icoApp = IconoOnda(Azul));
        }

        // Junto al reloj: el ícono de la app con un punto del color del estado abajo a la derecha
        // (verde conectado, ámbar conectando, naranja IA no lista, rojo sin conexión).
        public static Icon Icono(Color estado)
        {
            try
            {
                int lado = SystemInformation.SmallIconSize.Width;
                if (lado < 16) lado = 16;
                using (var chico = new Icon(IconoApp(), lado, lado))
                using (var dib = chico.ToBitmap())
                using (var bmp = new Bitmap(lado, lado, PixelFormat.Format32bppArgb))
                {
                    using (var g = Graphics.FromImage(bmp))
                    {
                        g.Clear(Color.Transparent);
                        g.DrawImage(dib, new Rectangle(0, 0, lado, lado));
                        g.SmoothingMode = SmoothingMode.AntiAlias;
                        float d = (float)Math.Round(lado * 0.42), borde = Math.Max(1.5f, lado / 11f);
                        float x = lado - d, y = lado - d;
                        using (var b = new SolidBrush(Color.FromArgb(0x0f, 0x17, 0x2a)))
                            g.FillEllipse(b, x - 0.5f, y - 0.5f, d + 0.5f, d + 0.5f);
                        using (var b = new SolidBrush(ColorPunto(estado)))
                            g.FillEllipse(b, x + borde - 0.5f, y + borde - 0.5f, d - 2 * borde + 0.5f, d - 2 * borde + 0.5f);
                    }
                    IntPtr hi = bmp.GetHicon();
                    var ico = (Icon)Icon.FromHandle(hi).Clone();
                    try { DestroyIcon(hi); } catch { }
                    return ico;
                }
            }
            catch { return IconoOnda(estado); }
        }

        // Colores más vivos para el punto, que tiene que verse chico y sobre fondo oscuro.
        static Color ColorPunto(Color c)
        {
            if (c == Verde) return Color.FromArgb(0x22, 0xc5, 0x5e);
            if (c == Ambar) return Color.FromArgb(0xf5, 0x9e, 0x0b);
            if (c == Naranja) return Color.FromArgb(0xf9, 0x73, 0x16);
            if (c == Rojo) return Color.FromArgb(0xef, 0x44, 0x44);
            if (c == Azul) return Color.FromArgb(0x60, 0xa5, 0xfa);
            return c;
        }

        // Ícono anterior (cinco barras de una onda, del color del estado). Solo de respaldo si falta el recurso.
        static Icon IconoOnda(Color c)
        {
            using (var bmp = new Bitmap(32, 32))
            {
                using (var g = Graphics.FromImage(bmp))
                using (var p = new Pen(c, 3.4f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.Clear(Color.Transparent);
                    int[] alto = { 5, 13, 22, 11, 5 };
                    for (int i = 0; i < 5; i++)
                    {
                        float x = 4 + i * 6f, h = alto[i];
                        g.DrawLine(p, x, 16 - h / 2, x, 16 + h / 2);
                    }
                }
                IntPtr hi = bmp.GetHicon();
                var ico = (Icon)Icon.FromHandle(hi).Clone();
                try { DestroyIcon(hi); } catch { }
                return ico;
            }
        }
    }
}
