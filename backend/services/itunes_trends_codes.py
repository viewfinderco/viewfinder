# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Various codes for iTunes Connect reports.

Source: http://www.apple.com/itunesnews/docs/AppStoreReportingInstructions.pdf (v7, 2012-11-06).

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'


# Meaning of field "product type identifier" (6th field, with 0 index). The value is what we use in our metric name.
# eg: an entry with key 1 will get turned into: itunes.downloads.<version>.<store country>
# The meaning is not always clear. So far, we have only seen downloads, updates, and purchases_in_app.
PRODUCT_TYPE_IDENTIFIER = {
  '1':   'downloads',                      # Free or paid app: iPhone and iPod touch (iOS)
  '7':   'updates',                        # Update: iPhone and iPod touch (iOS)
  'IA1': 'inapp_purchases',                # In-App Purchase: Purchase (iOS)
  'IA9': 'inapp_subscriptions',            # In-App Purchase: Subscription (iOS)
  'IAY': 'inapp_subscriptions_auto_renew', # In-App Purchase: Auto-renewable subscription (iOS)
  'IAC': 'inapp_subscriptions_free',       # In-App Purchase: Free subscription (iOS)
  '1F':  'downloads_universal',            # Free or Paid Apps: Universal (iOS)
  '7F':  'updates_universal',              # Updates: Universal (iOS)
  '1T':  'downloads_ipad',                 # Free or pair app: iPad (iOS)
  '7T':  'updates_ipad',                   # Update: iPad (iOS)
  'F1':  'downloads_mac',                  # Free or paid app: Mac app
  'F7':  'updates_mac',                    # Update: Mac app
  'FI1': 'purchases_in_app_mac',           # In-App Purchase: Mac app
  '1E':  'custom_iphone',                  # Paid app: Custom iPhone and iPod touch (iOS)
  '1EP': 'custom_ipad',                    # Paid app: Custom iPad (iOS)
  '1EU': 'custom_universal',               # Paid app: Custom universal (iOS)
}

# Country codes for the 12th field (0 indexed). Apple calls it the "app store territory".
# Apple's list is 126 short of the official ISO list which can be found at:
# http://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements
COUNTRY_CODE = {
  'AE': 'United Arab Emirates',
  'AG': 'Antigua and Barbuda',
  'AI': 'Anguilla',
  'AM': 'Armenia',
  'AO': 'Angola',
  'AR': 'Argentina',
  'AT': 'Austria',
  'AU': 'Australia',
  'AZ': 'Azerbaijan',
  'BB': 'Barbados',
  'BE': 'Belgium',
  'BG': 'Bulgaria',
  'BH': 'Bahrain',
  'BM': 'Bermuda',
  'BN': 'Brunei',
  'BO': 'Bolivia',
  'BR': 'Brazil',
  'BS': 'Bahamas',
  'BW': 'Botswana',
  'BY': 'Belarus',
  'BZ': 'Belize',
  'CA': 'Canada',
  'CH': 'Switzerland',
  'CL': 'Chile',
  'CN': 'China',
  'CO': 'Colombia',
  'CR': 'Costa Rica',
  'CY': 'Cyprus',
  'CZ': 'Czech Republic',
  'DE': 'Germany',
  'DK': 'Denmark',
  'DM': 'Dominica',
  'DO': 'Dominican Republic',
  'DZ': 'Algeria',
  'EC': 'Ecuador',
  'EE': 'Estonia',
  'EG': 'Egypt',
  'ES': 'Spain',
  'FI': 'Finland',
  'FR': 'France',
  'GB': 'United Kingdom',
  'GD': 'Grenada',
  'GH': 'Ghana',
  'GR': 'Greece',
  'GT': 'Guatemala',
  'GY': 'Guyana',
  'HK': 'Hong Kong',
  'HN': 'Honduras',
  'HR': 'Croatia',
  'HU': 'Hungary',
  'ID': 'Indonesia',
  'IE': 'Ireland',
  'IL': 'Israel',
  'IN': 'India',
  'IS': 'Iceland',
  'IT': 'Italy',
  'JM': 'Jamaica',
  'JO': 'Jordan',
  'JP': 'Japan',
  'KE': 'Kenya',
  'KN': 'St. Kitts and Nevis',
  'KR': 'Republic Of Korea',
  'KW': 'Kuwait',
  'KY': 'Cayman Islands',
  'KZ': 'Kazakstan',
  'LB': 'Lebanon',
  'LC': 'St. Lucia',
  'LK': 'Sri Lanka',
  'LT': 'Lithuania',
  'LU': 'Luxembourg',
  'LV': 'Latvia',
  'MD': 'Republic Of Moldova',
  'MG': 'Madagascar',
  'MK': 'Macedonia',
  'ML': 'Mali',
  'MO': 'Macau',
  'MS': 'Montserrat',
  'MT': 'Malta',
  'MU': 'Mauritius',
  'MX': 'Mexico',
  'MY': 'Malaysia',
  'NE': 'Niger',
  'NG': 'Nigeria',
  'NI': 'Nicaragua',
  'NL': 'Netherlands',
  'NO': 'Norway',
  'NZ': 'New Zealand',
  'OM': 'Oman',
  'PA': 'Panama',
  'PE': 'Peru',
  'PH': 'Philippines',
  'PK': 'Pakistan',
  'PL': 'Poland',
  'PT': 'Portugal',
  'PY': 'Paraguay',
  'QA': 'Qatar',
  'RO': 'Romania',
  'RU': 'Russia',
  'SA': 'Saudi Arabia',
  'SE': 'Sweden',
  'SG': 'Singapore',
  'SI': 'Slovenia',
  'SK': 'Slovakia',
  'SN': 'Senegal',
  'SR': 'Suriname',
  'SV': 'El Salvador',
  'TC': 'Turks and Caicos',
  'TH': 'Thailand',
  'TN': 'Tunisia',
  'TR': 'Turkey',
  'TT': 'Trinidad and Tobago',
  'TW': 'Taiwan',
  'TZ': 'Tanzania',
  'UG': 'Uganda',
  'US': 'United States',
  'UY': 'Uruguay',
  'UZ': 'Uzbekistan',
  'VC': 'St. Vincent and The Grenadines',
  'VE': 'Venezuela',
  'VG': 'British Virgin Islands',
  'VN': 'Vietnam',
  'YE': 'Yemen',
  'ZA': 'South Africa'
}

# Currency codes for the 11th and 13th fields (0 indexed). Apple calls them "customer currency" and
# "currency of proceeds" respectively.
CURRENCY_CODE = {
  'AUD': 'Australian Dollar',
  'CAD': 'Canadian Dollar',
  'CHF': 'Swiss Franc',
  'DKK': 'Danish Krone',
  'EUR': 'Euro',
  'GBP': 'Pound Sterling',
  'JPY': 'Japanese Yen',
  'MXN': 'Mexican Peso',
  'NOK': 'Norwegian Krone',
  'NZD': 'New Zealand Dollar',
  'SEK': 'Swedish Krona',
  'USD': 'United States Dollar'
}
