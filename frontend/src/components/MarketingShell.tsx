import { Header } from "./Header";
import { Footer } from "./Footer";

export function MarketingShell({
  children,
  current,
  jsonLd,
}: {
  children: React.ReactNode;
  current?: string;
  jsonLd?: object | object[];
}) {
  const ldArray = jsonLd ? (Array.isArray(jsonLd) ? jsonLd : [jsonLd]) : [];
  return (
    <>
      <Header current={current} />
      <main id="main">{children}</main>
      <Footer />
      {ldArray.map((obj, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(obj) }}
        />
      ))}
    </>
  );
}
