import { Highlight, type PrismTheme } from 'prism-react-renderer';
import { languageTitle, prismLanguage } from '@/shared/lib/highlight';
import classes from './CodeBlock.module.css';

interface CodeBlockProps {
  code: string;
  language?: string | null;
  label?: string;
}

const SCOUT_CODE_THEME: PrismTheme = {
  plain: { color: '#ece8f3', backgroundColor: 'transparent' },
  styles: [
    {
      types: ['comment', 'prolog', 'doctype', 'cdata'],
      style: { color: '#a39fb5', fontStyle: 'italic' },
    },
    { types: ['keyword', 'important', 'atrule', 'rule'], style: { color: '#ff85ac' } },
    { types: ['string', 'char', 'attr-value', 'regex', 'inserted'], style: { color: '#9fe3c4' } },
    { types: ['number', 'boolean', 'constant', 'symbol'], style: { color: '#ffc58a' } },
    { types: ['function', 'class-name', 'selector', 'builtin'], style: { color: '#cbc5f5' } },
    { types: ['tag', 'property', 'attr-name', 'variable'], style: { color: '#f2b8ff' } },
    { types: ['operator', 'punctuation', 'entity', 'url'], style: { color: '#c9c3d8' } },
    { types: ['deleted'], style: { color: '#ff85ac' } },
  ],
};

export function CodeBlock({ code, language, label }: CodeBlockProps) {
  // Тёмная плашка с подсветкой: код задания должен читаться как в редакторе.
  // Номера строк появляются только у длинных фрагментов, где на них удобно ссылаться.
  const title = label ?? languageTitle(language);
  const lines = code.replace(/\n+$/, '');
  const numbered = lines.split('\n').length > 3;

  return (
    <figure className={classes.root}>
      {title && <figcaption className={classes.caption}>{title}</figcaption>}
      <Highlight code={lines} language={prismLanguage(language)} theme={SCOUT_CODE_THEME}>
        {({ tokens, getLineProps, getTokenProps }) => (
          <pre className={classes.pre} data-numbered={numbered || undefined} tabIndex={0}>
            <code>
              {tokens.map((line, lineIndex) => (
                <span key={lineIndex} {...getLineProps({ line })} className={classes.line}>
                  {numbered && (
                    <span className={classes.number} aria-hidden="true">
                      {lineIndex + 1}
                    </span>
                  )}
                  <span>
                    {line.map((token, tokenIndex) => (
                      <span key={tokenIndex} {...getTokenProps({ token })} />
                    ))}
                  </span>
                </span>
              ))}
            </code>
          </pre>
        )}
      </Highlight>
    </figure>
  );
}
