# Changelog

## [0.2.0](https://github.com/AliNaveed01/agentgauge/compare/v0.1.0...v0.2.0) (2026-11-05)


### Features

* **bench:** add tool-use and judge benchmark for OpenAI-compatible endpoints ([e0a65af](https://github.com/AliNaveed01/agentgauge/commit/e0a65af1f197cd68edf1e1f87cce46d6cb62db87)), closes [#34](https://github.com/AliNaveed01/agentgauge/issues/34)
* **calibration:** add accuracy, confusion matrix and per-class precision and recall ([3270754](https://github.com/AliNaveed01/agentgauge/commit/327075468da08462bcb894dee763ae9fa9441e28)), closes [#30](https://github.com/AliNaveed01/agentgauge/issues/30)
* **calibration:** add Cohen's kappa with quadratic weighting ([951ed7c](https://github.com/AliNaveed01/agentgauge/commit/951ed7c86ab2eda807dae1d49ef4ae6cab64a711)), closes [#30](https://github.com/AliNaveed01/agentgauge/issues/30)
* **calibration:** add label format and loader with file and line errors ([f982609](https://github.com/AliNaveed01/agentgauge/commit/f9826094db7d20c8a99471478cc91733b1158ad3)), closes [#29](https://github.com/AliNaveed01/agentgauge/issues/29)
* **calibration:** add seeded bootstrap kappa interval and calibrate report ([582adb0](https://github.com/AliNaveed01/agentgauge/commit/582adb0d48d2a95f38090039ecab53105c184da5)), closes [#30](https://github.com/AliNaveed01/agentgauge/issues/30)
* **cli:** add calibrate command ([1861d14](https://github.com/AliNaveed01/agentgauge/commit/1861d14ac9f4eff040c28c8d1d16a5e17bc0aced)), closes [#31](https://github.com/AliNaveed01/agentgauge/issues/31)
* **cli:** render calibration reports with a kappa trust warning ([2502a90](https://github.com/AliNaveed01/agentgauge/commit/2502a903469d63754ae0f6a731e47d8afeb8dc4d)), closes [#31](https://github.com/AliNaveed01/agentgauge/issues/31)
* **core:** add provenance details to Score ([ae6250c](https://github.com/AliNaveed01/agentgauge/commit/ae6250c9ec108eed428ce6ef512e6c1caf3d2cdc)), closes [#27](https://github.com/AliNaveed01/agentgauge/issues/27)
* **core:** offer suite tools to the model on every case ([477e388](https://github.com/AliNaveed01/agentgauge/commit/477e3889a227aaf98903911619b743c9213fca0b)), closes [#34](https://github.com/AliNaveed01/agentgauge/issues/34)
* **judge:** add Rubric and Scale models ([7cdba9b](https://github.com/AliNaveed01/agentgauge/commit/7cdba9b6a96783bf6f21ee8e1aad389b94e05143)), closes [#26](https://github.com/AliNaveed01/agentgauge/issues/26)
* **judge:** add SQLite judge cache keyed by the full judge input ([e4c9918](https://github.com/AliNaveed01/agentgauge/commit/e4c991819847dcb916abfeccbf276652b2675d86)), closes [#28](https://github.com/AliNaveed01/agentgauge/issues/28)
* **judge:** add versioned prompt template and rendering ([b0c13bc](https://github.com/AliNaveed01/agentgauge/commit/b0c13bc2e65ff17a9c7ef485123caf17223ba5e8)), closes [#26](https://github.com/AliNaveed01/agentgauge/issues/26)
* **judge:** load rubrics from YAML with file and line errors ([00ba027](https://github.com/AliNaveed01/agentgauge/commit/00ba0277bcf657b93d974d2f4ff84c2d19ee3f7a)), closes [#26](https://github.com/AliNaveed01/agentgauge/issues/26)
* **judge:** parse and validate judge verdicts ([36df2dd](https://github.com/AliNaveed01/agentgauge/commit/36df2dd9fdfe9cfe2781f26d1ab50e4376adb6cb)), closes [#27](https://github.com/AliNaveed01/agentgauge/issues/27)
* **providers:** let the fake provider match responses by substring ([8ec5142](https://github.com/AliNaveed01/agentgauge/commit/8ec514292c3614a82bfbde52ffb8c503f14ae8a3)), closes [#32](https://github.com/AliNaveed01/agentgauge/issues/32)
* **runner:** close scorers that hold resources when a run ends ([d3b293f](https://github.com/AliNaveed01/agentgauge/commit/d3b293f34f692064687fe62fa77c49e8c4bddce0)), closes [#27](https://github.com/AliNaveed01/agentgauge/issues/27)
* **scorers:** add llm_judge scorer with one retry and provenance ([e812a77](https://github.com/AliNaveed01/agentgauge/commit/e812a77fd6f9f2dc9dffbfa130455ad47b69517f)), closes [#27](https://github.com/AliNaveed01/agentgauge/issues/27)
* **scorers:** add tool_call scorer ([c5adbeb](https://github.com/AliNaveed01/agentgauge/commit/c5adbeb8bdbbacac7960b455e8fbabd8f807fefe)), closes [#34](https://github.com/AliNaveed01/agentgauge/issues/34)
* **scorers:** serve llm_judge replies from the judge cache ([3c5f7b4](https://github.com/AliNaveed01/agentgauge/commit/3c5f7b4cdeb1c42997ac07469222d2c3a43cbc27)), closes [#28](https://github.com/AliNaveed01/agentgauge/issues/28)


### Bug Fixes

* **cli:** keep the confusion matrix title on one line ([8ba7a2f](https://github.com/AliNaveed01/agentgauge/commit/8ba7a2feb5a9ffe1a9736fca7bb7978e87e95c06)), closes [#31](https://github.com/AliNaveed01/agentgauge/issues/31)


### Documentation

* **adr:** record calibrate command decisions ([f71826a](https://github.com/AliNaveed01/agentgauge/commit/f71826a871a34655afd51e18943af919aeac6ff6)), closes [#31](https://github.com/AliNaveed01/agentgauge/issues/31)
* **adr:** record judge cache decisions ([a0ce978](https://github.com/AliNaveed01/agentgauge/commit/a0ce978e99396cf10119bd2c1161bd1ca493f5f1)), closes [#28](https://github.com/AliNaveed01/agentgauge/issues/28)
* **adr:** record label and calibration metric decisions ([8208ce7](https://github.com/AliNaveed01/agentgauge/commit/8208ce701f822051a757ebab72a852b7e38e0108)), closes [#30](https://github.com/AliNaveed01/agentgauge/issues/30)
* **adr:** record llm_judge scorer decisions ([ea6c883](https://github.com/AliNaveed01/agentgauge/commit/ea6c883cc23f6a34339942bb3d727a50759bd465)), closes [#27](https://github.com/AliNaveed01/agentgauge/issues/27)
* **adr:** record rubric and prompt template decisions ([a216a17](https://github.com/AliNaveed01/agentgauge/commit/a216a177473723bdeba4776728fe963cd40ecdc4)), closes [#26](https://github.com/AliNaveed01/agentgauge/issues/26)
* **adr:** record tool-use benchmark decisions ([90f4c9e](https://github.com/AliNaveed01/agentgauge/commit/90f4c9e98a4e3261bc49dd249ec23ce460371f0b)), closes [#34](https://github.com/AliNaveed01/agentgauge/issues/34)
* **bench:** add qwen3:0.6b results on local Ollama ([86e72d8](https://github.com/AliNaveed01/agentgauge/commit/86e72d8740d127f05556d21d7d688d2532caa341)), closes [#34](https://github.com/AliNaveed01/agentgauge/issues/34)
* document installing from PyPI ([dcc31b0](https://github.com/AliNaveed01/agentgauge/commit/dcc31b067cbc1337f8b50439323154a0de9b1e4d))
* **examples:** add a judge calibration example ([53a05a6](https://github.com/AliNaveed01/agentgauge/commit/53a05a6bc34c0bd1a55d63efc099be8734c20e22)), closes [#32](https://github.com/AliNaveed01/agentgauge/issues/32)
* explain judge calibration ([bc485c5](https://github.com/AliNaveed01/agentgauge/commit/bc485c58c007bbdb6a73398f4e6d2f46345ab005)), closes [#32](https://github.com/AliNaveed01/agentgauge/issues/32)
* mention the llm_judge scorer and calibrate in the README ([795178c](https://github.com/AliNaveed01/agentgauge/commit/795178cbd20c67e24c8392dcfe92d0d78d2f2192)), closes [#32](https://github.com/AliNaveed01/agentgauge/issues/32)

## [0.1.0](https://github.com/AliNaveed01/agentgauge/compare/v0.0.1...v0.1.0) (2026-11-04)


### Features

* **cli:** add run command ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([b82b0a3](https://github.com/AliNaveed01/agentgauge/commit/b82b0a30d66f4d88368901fb0da35b59161039d7))
* **cli:** add runs list command ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([9b77fc2](https://github.com/AliNaveed01/agentgauge/commit/9b77fc2a1a044c688241bac93fe535af4a3c02cb))
* **cli:** add runs show command ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([7619801](https://github.com/AliNaveed01/agentgauge/commit/76198017ae97e894f96e66f3dd08b1059aa3ba89))
* **cli:** add typer app and agentgauge entry point ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([cd1b4bc](https://github.com/AliNaveed01/agentgauge/commit/cd1b4bc616024b8296e3b3e9b8a85c2f85d5cb9d))
* **cli:** render runs and run lists as Rich tables ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([e20030d](https://github.com/AliNaveed01/agentgauge/commit/e20030d544416cff369c0904fec782c1d8170fa6))
* **core:** add CaseResult.passed ([#8](https://github.com/AliNaveed01/agentgauge/issues/8)) ([8ef4ce7](https://github.com/AliNaveed01/agentgauge/commit/8ef4ce73d958323bf5bb0f3dc00f36b96132ec98))
* **core:** add chat request, tool and params models ([60827aa](https://github.com/AliNaveed01/agentgauge/commit/60827aa48c84adc8d64180758fe82815b03603bf))
* **core:** add frozen domain models ([5c3fb2b](https://github.com/AliNaveed01/agentgauge/commit/5c3fb2b1f5be55e2fb6ed8b7052c286e50ad3520))
* **core:** add optional provider config to Suite ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([47c0463](https://github.com/AliNaveed01/agentgauge/commit/47c0463f8657e690f2d827ea06d035a5a127adbd))
* **core:** add ScorerSpec and accept it in Suite scorers ([#6](https://github.com/AliNaveed01/agentgauge/issues/6)) ([897f7e8](https://github.com/AliNaveed01/agentgauge/commit/897f7e87b413cda7a7b66d2b6b1261f10550a6d7))
* **core:** add tool_calls to Message with role validation ([93a62a7](https://github.com/AliNaveed01/agentgauge/commit/93a62a7cd9f90046f03ebf78b2bdd5310a88dba8))
* **core:** add YAML and JSONL suite loader ([73bac6e](https://github.com/AliNaveed01/agentgauge/commit/73bac6eb5d77d11e72ca39dad33103b8068e6888))
* **core:** record latency and cost on CaseResult ([#8](https://github.com/AliNaveed01/agentgauge/issues/8)) ([3fccd33](https://github.com/AliNaveed01/agentgauge/commit/3fccd3345b10795372fb004b0b8485d0870d3f4a))
* **providers:** add deterministic FakeProvider ([771e00b](https://github.com/AliNaveed01/agentgauge/commit/771e00b40a10d1801ab4c799c04dd4b1e3efe3ff))
* **providers:** add OpenAI-compatible adapter ([6a665a3](https://github.com/AliNaveed01/agentgauge/commit/6a665a399132fab5f33e21463e494380402d3a28))
* **providers:** add Provider protocol ([b001189](https://github.com/AliNaveed01/agentgauge/commit/b001189c800fece73b3e20bebbb97b7a1c880c85))
* **providers:** add ProviderError ([5222745](https://github.com/AliNaveed01/agentgauge/commit/5222745622b82af73d881ad0b382086b89c63e5a))
* **providers:** build providers from config ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([4e03a3b](https://github.com/AliNaveed01/agentgauge/commit/4e03a3b0b6d5e18df2925da05416a1121d3a3caf))
* **providers:** count tool calls in fake prompt tokens ([e33ac6c](https://github.com/AliNaveed01/agentgauge/commit/e33ac6c1b3558619f083ec47829d6cf6ac1ef808))
* **runner:** add run_suite to execute and score a suite ([#8](https://github.com/AliNaveed01/agentgauge/issues/8)) ([bbfeeb9](https://github.com/AliNaveed01/agentgauge/commit/bbfeeb9356c72e5fec9e6b773f871a283cbc389f))
* **runner:** bound in-flight cases with a concurrency limit ([#8](https://github.com/AliNaveed01/agentgauge/issues/8)) ([0df1200](https://github.com/AliNaveed01/agentgauge/commit/0df12005ea95a582ea186e29907de88941abcac2))
* **runner:** record case failures without aborting the run ([#8](https://github.com/AliNaveed01/agentgauge/issues/8)) ([5a617b1](https://github.com/AliNaveed01/agentgauge/commit/5a617b1dd2ec9b3d4d11513e0d33b4c9a8f9ee20))
* **scorers:** add contains scorer ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([0a28614](https://github.com/AliNaveed01/agentgauge/commit/0a286148e9f913875dd589cdd921c9e2f85c5baf))
* **scorers:** add exact_match scorer ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([8c3ffac](https://github.com/AliNaveed01/agentgauge/commit/8c3ffac9ca29d7b84006d484bbe2df4a4b70e6bf))
* **scorers:** add JSON Schema subset validator ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([21bfa95](https://github.com/AliNaveed01/agentgauge/commit/21bfa957ef4dfb847fcb0b50549405215db081f9))
* **scorers:** add json_schema scorer ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([f2f0be8](https://github.com/AliNaveed01/agentgauge/commit/f2f0be8f8f4dca1697a89dd27e9159b8cdb07257))
* **scorers:** add name-based scorer registry ([#6](https://github.com/AliNaveed01/agentgauge/issues/6)) ([3941775](https://github.com/AliNaveed01/agentgauge/commit/3941775186524841b962b03b890c40bee500e626))
* **scorers:** add numeric_tolerance scorer ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([6614c29](https://github.com/AliNaveed01/agentgauge/commit/6614c293c96c001d39d051b02bcdc0d79bd9c006))
* **scorers:** add regex scorer ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([de5ffde](https://github.com/AliNaveed01/agentgauge/commit/de5ffde0a0207a8930ff1a842de219bd9374ae0c))
* **scorers:** add Scorer protocol ([#6](https://github.com/AliNaveed01/agentgauge/issues/6)) ([9c56bb2](https://github.com/AliNaveed01/agentgauge/commit/9c56bb2fa4f9e51e53ec739d48810e54ac19e7f0))
* **storage:** add get_run with unique id prefix lookup ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([305b0b6](https://github.com/AliNaveed01/agentgauge/commit/305b0b674b18d098fc17d290ec6e323f501f242d))
* **storage:** add initial runs and case_results schema ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([541797d](https://github.com/AliNaveed01/agentgauge/commit/541797dc2c0d3af1c047ff3ebe9f849dc2eb4bfb))
* **storage:** add list_runs with outcome summaries ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([49f5317](https://github.com/AliNaveed01/agentgauge/commit/49f53177a7ad679bd9a75b5b6273a8ea6320a901))
* **storage:** add RunStore with save_run ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([62eaae6](https://github.com/AliNaveed01/agentgauge/commit/62eaae61e3417e9c8713a13f1b9ba993616c248b))
* **storage:** add schema migration runner ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([353d8f8](https://github.com/AliNaveed01/agentgauge/commit/353d8f869eb7df665ed1e82df51acf4ec77d935b))


### Bug Fixes

* **storage:** close the connection when opening the store fails ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([18cd2f5](https://github.com/AliNaveed01/agentgauge/commit/18cd2f5e2f52d89bce205be28126ba6b8dcbb525))


### Documentation

* add ADR 0001 on recording decisions ([31c6c51](https://github.com/AliNaveed01/agentgauge/commit/31c6c51ebc6525a91aecd5c06e82cd096ee3ace8))
* add ADR 0002 on the provider interface ([d8a990c](https://github.com/AliNaveed01/agentgauge/commit/d8a990c0dc2304c8ed306e33f3124ae5190ef1bb))
* add ADR 0003 on scorer interface and registry ([#6](https://github.com/AliNaveed01/agentgauge/issues/6)) ([7d21894](https://github.com/AliNaveed01/agentgauge/commit/7d21894c3f55bf22e22be4daa6a4e5a33306680f))
* add ADR 0004 on deterministic scorer semantics ([#7](https://github.com/AliNaveed01/agentgauge/issues/7)) ([9448f8b](https://github.com/AliNaveed01/agentgauge/commit/9448f8bb3d3084cb0157cecbfcb29eb4325c6bd9))
* add ADR 0005 on runner semantics ([#8](https://github.com/AliNaveed01/agentgauge/issues/8)) ([60eaad7](https://github.com/AliNaveed01/agentgauge/commit/60eaad7b2ebef9a4337ac5ec269b5879147292c0))
* add ADR 0006 on run storage ([#9](https://github.com/AliNaveed01/agentgauge/issues/9)) ([c9a07dd](https://github.com/AliNaveed01/agentgauge/commit/c9a07dd8427bdd5fc469737b0c1ae2551ac420cf))
* add ADR 0007 on CLI behaviour and suite provider config ([#10](https://github.com/AliNaveed01/agentgauge/issues/10)) ([43755e8](https://github.com/AliNaveed01/agentgauge/commit/43755e800fad1ffde7594db398bd9ea33bb5e135))
* add code of conduct ([7e9a57d](https://github.com/AliNaveed01/agentgauge/commit/7e9a57d4ec67eb99215abc958426167248226c12))
* add contributing guide ([cf2fdf0](https://github.com/AliNaveed01/agentgauge/commit/cf2fdf014b67c24973172ad258a8e607692600ce))
* add issue and pull request templates ([d88521a](https://github.com/AliNaveed01/agentgauge/commit/d88521a99e12634db03753ee3f0a46aa20afb888))
* add security policy ([3f8e1d9](https://github.com/AliNaveed01/agentgauge/commit/3f8e1d9003988b3c476abcfead2e0d423e5842a9))
* **examples:** add basic example suite on the fake provider ([#11](https://github.com/AliNaveed01/agentgauge/issues/11)) ([7d3ddf3](https://github.com/AliNaveed01/agentgauge/commit/7d3ddf323c44bb8e143e6fe14173482d21b70ced))
* update ADR 0002 for tool-call messages ([7044009](https://github.com/AliNaveed01/agentgauge/commit/704400928cebaf82e1cba3214b5cc12ab4c2818a))
* write README quickstart and suite guide ([#11](https://github.com/AliNaveed01/agentgauge/issues/11)) ([9e12c2f](https://github.com/AliNaveed01/agentgauge/commit/9e12c2fbd77065391accd62570d2c18d3e6eab94))
