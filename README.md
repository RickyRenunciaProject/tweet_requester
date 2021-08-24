# Tweet Requester

A python package, published under the [MIT License][6]. The package is used to retrieve, cache and interact with tweet status data dictionaries utilizing the [Twitter API `1.1`][1].

## \#RickyRenuncia Project

This package was develop for the [RickyRenunciaProject Team][2] for their indepent capture preservation and description of manifestations and protests through social media as seen at their [scalar book][3]. This library evolved to function as source code for a [Case Module][4] but may prove useful for other environments.

## License

This project is released under an [MIT License][6].

## How To Use

The main purpose of this library is obtaining data from the Twitter API 1.1 based on a list of tweet IDs.

The `TSess` class manages communication and caching and is used as a parameter for the `TweetAnalyzer`, `TweetInteractiveClassifier` and `JsonLInteractiveClassifier`. 

* `TweetAnalyzer` class manages most of the automatic data extraction from the data dictionary.
* `TweetInteractiveClassifier` is based on the TweetAnalyzer but includes functionality directed to interacting with the tweet in an IPython environment.
* `JsonLInteractiveClassifier` is an interactive GUI and database manager that allows capturing additional metadata from user interaction... 

To seet an example of how to use the library, please visit the [Cases Module][4] or try it at [Not yet published].

## Future

Current approach is project specific but we are working on a proposal to design custom interfaces based on `YAML`/`JSON` templates.

### **TODO:**

- Include mention of [twitter policies][5].
- Continue project description.
- Include example of usage.
- Suggest using the Case Module.
- Mention and show IPython interactive appraisal.

[1]: https://developer.twitter.com/en/docs/twitter-api/v1 "Twitter API 1 at developer.twitter.com"
[2]: https://github.com/RickyRenunciaProject "RickyRenunciaProject at Github"
[3]: https://libarchivist.com/rrp/rickyrenuncia/index "RickyRenuncia Scaler Book"
[4]: https://github.com/RickyRenunciaProject/RickyRenuncia-case-module "RickyRenuncia Case Module"
[5]: https://developer.twitter.com/en/developer-terms/agreement-and-policy "Developer Agreement and Policy | Twitter"
[6]: https://opensource.org/licenses/MIT "MIT License"