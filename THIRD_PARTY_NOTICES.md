# Third-party references and notices

VitalDock is an independent implementation. No upstream source files or fixture
files are vendored. Format compatibility was informed by these projects:

- JordyThien/Huawei-Health-Importer, MIT, copyright (c) 2026 Jordy Thien.
- christianeirich/huawei-health-to-health-connect, MIT, copyright (c) 2025 Christian Eirich.
- CTHRU/Hitrava, current NPOSL-3.0; consulted as documentation, no code copied.
- HMS-Core/hms-health-demo-java, Apache-2.0; consulted as official documentation.
- mvilanova/intervals-mcp-server, GPL-3.0; read its README for agent integration
  scope, no code or configuration copied. VitalDock live tools are independent.

Links and exact reference revisions are recorded in [docs/research.md](docs/research.md).
The following MIT notice is retained for the two format references above:

```text
MIT License

Copyright (c) 2026 Jordy Thien
Copyright (c) 2025 Christian Eirich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The optional `mcp` SDK, `keyring` and development tools are external dependencies,
not included in this repository. Their respective licenses apply to those packages.
Huawei and other vendor names refer to data sources and do not imply affiliation.

The Android companion uses AndroidX Activity/Lifecycle and Health Connect 1.1.0
(Apache-2.0), Kotlin and kotlinx.coroutines (Apache-2.0), and NanoHTTPD 2.3.1
(BSD-3-Clause). They are resolved by Gradle; their respective licenses apply to
compiled distributions. Android builds do not contain health data or pairing keys.
The companion and USB client are independently implemented from the official SDK
documentation; no third-party Health Connect bridge source is copied.
