const { expect } = require('chai');
const { convert } = require('../src/converter');

describe('converter.convert()', () => {
  describe('basic HTML conversion', () => {
    it('converts simple paragraph to markdown', () => {
      const html = '<html><body><p>Hello world</p></body></html>';
      const result = convert(html);
      expect(result).to.have.property('markdown');
      expect(result).to.have.property('title');
      expect(result.markdown).to.include('Hello world');
    });

    it('converts headings correctly', () => {
      const html = '<html><body><article><h1>Main Title</h1><h2>Sub</h2><p>Text</p></article></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('# Main Title');
      expect(result.markdown).to.include('## Sub');
    });

    it('converts bold and italic', () => {
      const html = '<html><body><p><strong>bold</strong> and <em>italic</em></p></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('**bold**');
      expect(result.markdown).to.include('_italic_');
    });

    it('converts links', () => {
      const html = '<html><body><p><a href="https://example.com">click here</a></p></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('[click here](https://example.com');
    });

    it('converts unordered lists', () => {
      const html = '<html><body><ul><li>one</li><li>two</li><li>three</li></ul></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('one');
      expect(result.markdown).to.include('two');
      expect(result.markdown).to.include('three');
    });

    it('converts blockquotes', () => {
      const html = '<html><body><blockquote><p>A wise quote</p></blockquote></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('> A wise quote');
    });
  });

  describe('article extraction (Readability)', () => {
    it('extracts article content, strips nav/footer', () => {
      const html = `<html><head><title>Test</title></head><body>
        <nav>Menu</nav>
        <article>
          <h1>Test Article</h1>
          <p>Content here. This is the first paragraph of the article with enough text for Readability to recognise it as article content.</p>
          <p>This second paragraph adds more substance so Readability properly identifies the article boundaries and strips surrounding navigation elements.</p>
          <p>A third paragraph ensures the article body has sufficient length that the extraction algorithm works correctly and strips nav and footer elements.</p>
        </article>
        <footer>Copyright</footer>
      </body></html>`;
      const result = convert(html);
      expect(result.title).to.be.oneOf(['Test', 'Test Article']);
      expect(result.markdown).to.include('# Test Article');
      expect(result.markdown).to.include('Content here');
      expect(result.markdown).to.not.include('Menu');
      expect(result.markdown).to.not.include('Copyright');
    });

    it('extracts title from Readability parse', () => {
      const html = `<html><head><title>Page Title</title></head><body>
        <article><h1>Article Heading</h1><p>Some content paragraph for readability to find.</p><p>Another paragraph with more text.</p></article>
      </body></html>`;
      const result = convert(html);
      expect(result.title).to.be.a('string');
      expect(result.title.length).to.be.greaterThan(0);
    });

    it('falls back to full body when Readability returns null', () => {
      // Minimal HTML that Readability can't extract an article from
      const html = '<html><body><p>Just a lonely paragraph</p></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('Just a lonely paragraph');
      expect(result.title).to.be.a('string');
    });
  });

  describe('image conversion', () => {
    it('converts img tags to markdown image syntax', () => {
      const html = '<html><body><article><h1>Photos</h1><p>Look at this:</p><img src="photo.jpg" alt="A photo"><p>Nice right?</p></article></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('![A photo](');
      expect(result.markdown).to.include('photo.jpg');
    });

    it('handles images without alt text', () => {
      const html = '<html><body><article><h1>Photos</h1><p>Here:</p><img src="pic.png"><p>Done.</p></article></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('pic.png');
    });
  });

  describe('code block preservation', () => {
    it('preserves code blocks', () => {
      const html = `<html><body><article><h1>Code</h1><p>Example:</p><pre><code>console.log('hi')</code></pre><p>End.</p></article></body></html>`;
      const result = convert(html);
      expect(result.markdown).to.include("console.log('hi')");
      // Should be in a code block (backtick-fenced or indented)
      expect(result.markdown).to.match(/```[\s\S]*console\.log/);
    });

    it('preserves inline code', () => {
      const html = '<html><body><article><h1>Code</h1><p>Use <code>npm install</code> to install.</p></article></body></html>';
      const result = convert(html);
      expect(result.markdown).to.include('`npm install`');
    });
  });

  describe('table conversion (GFM)', () => {
    it('converts HTML tables to markdown tables', () => {
      const html = `<html><body><article><h1>Data</h1>
        <table>
          <thead><tr><th>Name</th><th>Age</th></tr></thead>
          <tbody><tr><td>Alice</td><td>30</td></tr><tr><td>Bob</td><td>25</td></tr></tbody>
        </table>
        <p>End of table.</p>
      </article></body></html>`;
      const result = convert(html);
      expect(result.markdown).to.include('Name');
      expect(result.markdown).to.include('Alice');
      expect(result.markdown).to.include('Bob');
      // GFM table should have pipe separators
      expect(result.markdown).to.include('|');
    });
  });

  describe('edge cases', () => {
    it('handles empty string HTML', () => {
      const result = convert('');
      expect(result).to.deep.equal({ markdown: '', title: 'Untitled' });
    });

    it('handles null HTML', () => {
      const result = convert(null);
      expect(result).to.deep.equal({ markdown: '', title: 'Untitled' });
    });

    it('handles undefined HTML', () => {
      const result = convert(undefined);
      expect(result).to.deep.equal({ markdown: '', title: 'Untitled' });
    });

    it('handles malformed HTML gracefully', () => {
      const html = '<html><body><p>Unclosed paragraph<div>Mixed <b>tags</p></div>';
      const result = convert(html);
      expect(result).to.have.property('markdown');
      expect(result).to.have.property('title');
      // Should not throw
    });

    it('handles HTML with only whitespace body', () => {
      const html = '<html><body>   </body></html>';
      const result = convert(html);
      expect(result).to.have.property('markdown');
      expect(result).to.have.property('title');
    });

    it('handles HTML with no body tag', () => {
      const html = '<p>No body wrapper</p>';
      const result = convert(html);
      expect(result.markdown).to.include('No body wrapper');
    });
  });

  describe('title extraction', () => {
    it('uses Readability title when available', () => {
      const html = `<html><head><title>Page Title</title></head><body>
        <article><h1>Article Title</h1><p>Content goes here with enough text for readability.</p><p>More content here.</p></article>
      </body></html>`;
      const result = convert(html);
      expect(result.title).to.be.a('string');
      expect(result.title.length).to.be.greaterThan(0);
    });

    it('returns "Untitled" when no title found', () => {
      const html = '<html><body><p>No title anywhere</p></body></html>';
      const result = convert(html);
      expect(result.title).to.equal('Untitled');
    });
  });
});
